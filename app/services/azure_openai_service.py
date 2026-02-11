import logging

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field

from app.config import Settings
from app.models.schemas import (
    CodeIssue,
    IssueSeverity,
    IssueType,
    PRFile,
    ReviewAnalysis,
    ReviewEvent,
)
from app.utils.diff_parser import DiffParser

logger = logging.getLogger(__name__)


REVIEW_INSTRUCTIONS = """You are an expert code reviewer with deep knowledge of software engineering best practices, security vulnerabilities, performance optimization, and clean code principles.

Your task is to analyze code changes (diffs) from a Pull Request and provide a thorough review.

For each issue you find, provide:
1. The exact file path
2. The line number where the issue occurs - MUST be a line number that appears with a '+' prefix in the diff
3. Severity level: critical, high, medium, low, or info
4. Issue type: bug, security, performance, style, maintainability, or best_practice
5. A clear description of the issue
6. A concrete suggestion for how to fix it (with code if applicable)

CRITICAL: Line numbers MUST correspond to lines that were actually changed in the diff (marked with +).
Only comment on lines that are visible in the diff with a '+' prefix.
If you want to comment on context, pick the nearest changed line.

For each file, you will see:
- Changed line ranges: The specific line numbers that were modified (these are the ONLY valid lines for comments)
- The diff showing what changed
- Full file content for context

Guidelines:
- Focus on meaningful issues that impact code quality, security, or functionality
- ONLY use line numbers from the "Changed lines" list provided for each file
- Avoid nitpicking on minor style issues unless they significantly impact readability
- For security issues, explain the potential vulnerability and its impact
- For bugs, explain what could go wrong and under what conditions
- Provide actionable suggestions with example code when possible
- Consider the context of changes - don't review unchanged code

The approval_recommendation should be:
- "APPROVE" if the code is good with only minor suggestions
- "REQUEST_CHANGES" if there are critical or high severity issues that must be fixed
- "COMMENT" if there are medium/low issues or general feedback

If there are no issues, return an empty issues array with a positive summary."""


class CodeReviewResult(BaseModel):
    """Structured output format for code review."""
    issues: list[CodeIssue] = Field(default_factory=list, description="List of code issues found")
    summary: str = Field(..., description="Overall assessment of the PR changes")
    approval_recommendation: ReviewEvent = Field(
        default=ReviewEvent.COMMENT,
        description="Recommendation: APPROVE, REQUEST_CHANGES, or COMMENT"
    )


class AzureOpenAIService:
    """Service for code analysis using Azure OpenAI with Microsoft Agent Framework."""

    def __init__(self, settings: Settings):
        """Initialize Azure OpenAI service with Agent Framework."""
        self.settings = settings

        # Create AzureOpenAIChatClient for Azure OpenAI
        client_kwargs: dict = {
            "deployment_name": settings.azure_openai_deployment,
            "api_version": settings.azure_openai_api_version,
            "endpoint": settings.azure_openai_endpoint,
            "credential": DefaultAzureCredential()
        }

        model_client = AzureOpenAIChatClient(**client_kwargs)

        self.review_agent = Agent(
            model_client,
            instructions=REVIEW_INSTRUCTIONS,
            name="code_reviewer",
            default_options={"response_format": CodeReviewResult},
        )

    def _build_review_prompt(
        self,
        pr_title: str,
        pr_body: str | None,
        files: list[PRFile],
        file_contents: dict[str, str | None],
        rag_context: str | None = None,
    ) -> str:
        """
        Build the user prompt for code review.

        Args:
            pr_title: PR title
            pr_body: PR description
            files: List of changed files with patches
            file_contents: Dict mapping filename to full file content

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "# Pull Request Review Request\n",
            f"## PR Title: {pr_title}\n",
        ]

        if pr_body:
            prompt_parts.append(f"## PR Description:\n{pr_body}\n")

        if rag_context:
            prompt_parts.append("## Code Standards (Azure AI Search)")
            prompt_parts.append(
                "Use the following standards as authoritative guidance for this review."
            )
            prompt_parts.append(rag_context)
            prompt_parts.append("\n---\n")

        prompt_parts.append("\n## Changed Files:\n")

        for file in files:
            if not file.patch:
                continue

            prompt_parts.append(f"\n### File: {file.filename}")
            prompt_parts.append(f"Status: {file.status} (+{file.additions}/-{file.deletions})")

            # Extract changed line numbers from the patch
            changed_lines = DiffParser.parse_patch(file.patch).get('RIGHT', set())
            if changed_lines:
                line_ranges = DiffParser.get_changed_line_ranges(file.patch)
                ranges_str = ", ".join([f"{start}-{end}" if start != end else str(start)
                                       for start, end in line_ranges])
                prompt_parts.append(f"**Changed lines (ONLY these lines can be commented on):** {ranges_str}")

            # Include full file content for context if available
            if file.filename in file_contents and file_contents[file.filename]:
                prompt_parts.append("\n#### Full File Content (for context):")
                prompt_parts.append(f"```\n{file_contents[file.filename]}\n```")

            prompt_parts.append("\n#### Diff/Patch:")
            prompt_parts.append(f"```diff\n{file.patch}\n```\n")

        prompt_parts.append("\nPlease review the above changes and provide your analysis in JSON format.")

        return "\n".join(prompt_parts)

    async def analyze_code(
        self,
        pr_title: str,
        pr_body: str | None,
        files: list[PRFile],
        file_contents: dict[str, str | None],
        rag_context: str | None = None,
    ) -> ReviewAnalysis:
        """
        Analyze code changes and generate review using Agent Framework.

        Args:
            pr_title: PR title
            pr_body: PR description
            files: List of changed files with patches
            file_contents: Dict mapping filename to full file content
            rag_context: Optional RAG context from Azure AI Search

        Returns:
            ReviewAnalysis with issues and recommendations
        """
        # Filter files with patches
        reviewable_files = [f for f in files if f.patch]

        if not reviewable_files:
            return ReviewAnalysis(
                issues=[],
                summary="No reviewable code changes found in this PR.",
                approval_recommendation=ReviewEvent.APPROVE,
                files_reviewed=0,
                total_issues=0,
                critical_issues=0,
            )

        user_prompt = self._build_review_prompt(
            pr_title, pr_body, reviewable_files, file_contents, rag_context
        )

        try:
            # Run agent with structured output
            response = await self.review_agent.run(messages=user_prompt)

            # Agent Framework returns structured response via .value
            result: CodeReviewResult = (
                response.value
                if isinstance(response.value, CodeReviewResult)
                else CodeReviewResult.model_validate_json(response.value)
            )

            # Validate and filter issues based on diff line numbers
            valid_issues = []
            invalid_lines = []

            for issue in result.issues:
                try:
                    # Find the corresponding file to check the patch
                    file_obj = next((f for f in reviewable_files if f.filename == issue.file), None)
                    if file_obj and file_obj.patch and not DiffParser.is_valid_comment_line(file_obj.patch, issue.line, 'RIGHT'):
                        # Try to find nearest valid line
                        nearest_line = DiffParser.find_nearest_valid_line(file_obj.patch, issue.line)
                        if nearest_line:
                            logger.warning(
                                f"Issue at {issue.file}:{issue.line} is invalid, "
                                f"adjusting to nearest valid line {nearest_line}"
                            )
                            # Create new issue with corrected line number
                            issue = CodeIssue(
                                file=issue.file,
                                line=nearest_line,
                                end_line=issue.end_line,
                                severity=issue.severity,
                                type=issue.type,
                                description=issue.description,
                                suggestion=issue.suggestion,
                                original_code=issue.original_code,
                            )
                        else:
                            invalid_lines.append(f"{issue.file}:{issue.line}")
                            logger.warning(
                                f"Skipping issue at {issue.file}:{issue.line} - "
                                "line not in diff, no nearby valid line found"
                            )
                            continue

                    valid_issues.append(issue)

                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to validate issue: {e}, issue: {issue}")
                    continue

            if invalid_lines:
                logger.info(f"Filtered out {len(invalid_lines)} issues with invalid line numbers")

            # Count critical issues
            critical_count = sum(
                1 for i in valid_issues
                if i.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH)
            )

            return ReviewAnalysis(
                issues=valid_issues,
                summary=result.summary,
                approval_recommendation=result.approval_recommendation,
                files_reviewed=len(reviewable_files),
                total_issues=len(valid_issues),
                critical_issues=critical_count,
            )

        except Exception as e:
            logger.error(f"Agent Framework error: {e}")
            return ReviewAnalysis(
                issues=[],
                summary=f"Failed to complete review: {e}",
                approval_recommendation=ReviewEvent.COMMENT,
                files_reviewed=len(reviewable_files),
                total_issues=0,
                critical_issues=0,
            )

    def format_issue_as_github_comment(self, issue: CodeIssue) -> str:
        """
        Format a code issue as a GitHub-compatible markdown comment.

        Args:
            issue: CodeIssue to format

        Returns:
            Formatted markdown string
        """
        severity_emoji = {
            IssueSeverity.CRITICAL: "🚨",
            IssueSeverity.HIGH: "⚠️",
            IssueSeverity.MEDIUM: "📝",
            IssueSeverity.LOW: "💡",
            IssueSeverity.INFO: "ℹ️",
        }

        type_labels = {
            IssueType.BUG: "Bug",
            IssueType.SECURITY: "Security",
            IssueType.PERFORMANCE: "Performance",
            IssueType.STYLE: "Style",
            IssueType.MAINTAINABILITY: "Maintainability",
            IssueType.BEST_PRACTICE: "Best Practice",
        }

        emoji = severity_emoji.get(issue.severity, "📝")
        label = type_labels.get(issue.type, "Issue")

        comment_parts = [
            f"{emoji} **{label}** ({issue.severity.value})\n",
            f"{issue.description}\n",
        ]

        if issue.suggestion:
            # Use GitHub suggestion block for code suggestions
            if "```" not in issue.suggestion and "\n" in issue.suggestion:
                comment_parts.append(f"\n```suggestion\n{issue.suggestion}\n```")
            else:
                comment_parts.append(f"\n**Suggestion:** {issue.suggestion}")

        return "\n".join(comment_parts)

    def format_review_summary(self, analysis: ReviewAnalysis) -> str:
        """
        Format the complete review analysis as a summary comment.

        Args:
            analysis: ReviewAnalysis to format

        Returns:
            Formatted markdown string
        """
        parts = [
            "# 🤖 AI Code Review Summary\n",
            f"**Files Reviewed:** {analysis.files_reviewed}",
            f"**Issues Found:** {analysis.total_issues}",
            f"**Critical/High Issues:** {analysis.critical_issues}\n",
            f"## Summary\n{analysis.summary}\n",
        ]

        if analysis.issues:
            parts.append("## Issues by Severity\n")

            # Group issues by severity
            severity_order = [
                IssueSeverity.CRITICAL,
                IssueSeverity.HIGH,
                IssueSeverity.MEDIUM,
                IssueSeverity.LOW,
                IssueSeverity.INFO,
            ]

            for severity in severity_order:
                severity_issues = [i for i in analysis.issues if i.severity == severity]
                if severity_issues:
                    parts.append(f"\n### {severity.value.title()} ({len(severity_issues)})\n")
                    for issue in severity_issues:
                        parts.append(f"- **{issue.file}:{issue.line}** - {issue.description}")

        recommendation_emoji = {
            ReviewEvent.APPROVE: "✅",
            ReviewEvent.REQUEST_CHANGES: "❌",
            ReviewEvent.COMMENT: "💬",
        }

        emoji = recommendation_emoji.get(analysis.approval_recommendation, "💬")
        parts.append(f"\n---\n{emoji} **Recommendation:** {analysis.approval_recommendation.value}")

        return "\n".join(parts)
