import json
import logging
from openai import AsyncAzureOpenAI

from app.config import Settings
from app.models.schemas import (
    CodeIssue, ReviewAnalysis, ReviewEvent, IssueSeverity, IssueType, PRFile
)
from app.utils.diff_parser import DiffParser


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert code reviewer with deep knowledge of software engineering best practices, security vulnerabilities, performance optimization, and clean code principles.

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

Your response must be valid JSON with this structure:
{
    "issues": [
        {
            "file": "path/to/file.py",
            "line": 42,
            "end_line": null,
            "severity": "high",
            "type": "bug",
            "description": "Description of the issue",
            "suggestion": "Suggested fix with code example",
            "original_code": "The problematic code snippet"
        }
    ],
    "summary": "Overall assessment of the PR changes",
    "approval_recommendation": "COMMENT"
}

The approval_recommendation should be:
- "APPROVE" if the code is good with only minor suggestions
- "REQUEST_CHANGES" if there are critical or high severity issues that must be fixed
- "COMMENT" if there are medium/low issues or general feedback

If there are no issues, return an empty issues array with a positive summary."""


class AzureOpenAIService:
    """Service for code analysis using Azure OpenAI."""
    
    def __init__(self, settings: Settings):
        """Initialize Azure OpenAI service."""
        self.settings = settings
        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
        self.deployment = settings.azure_openai_deployment
    
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
            f"# Pull Request Review Request\n",
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
                prompt_parts.append(f"\n#### Full File Content (for context):")
                prompt_parts.append(f"```\n{file_contents[file.filename]}\n```")
            
            prompt_parts.append(f"\n#### Diff/Patch:")
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
        Analyze code changes and generate review.
        
        Args:
            pr_title: PR title
            pr_body: PR description
            files: List of changed files with patches
            file_contents: Dict mapping filename to full file content
            
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
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from Azure OpenAI")
            
            result = json.loads(content)
            
            # Parse issues
            issues = []
            invalid_lines = []
            for issue_data in result.get("issues", []):
                try:
                    # Validate line number against the file's patch
                    file_name = issue_data["file"]
                    line_num = issue_data["line"]
                    
                    # Find the corresponding file to check the patch
                    file_obj = next((f for f in reviewable_files if f.filename == file_name), None)
                    if file_obj and file_obj.patch:
                        # Validate line number is in the changed lines
                        if not DiffParser.is_valid_comment_line(file_obj.patch, line_num, 'RIGHT'):
                            # Try to find nearest valid line
                            nearest_line = DiffParser.find_nearest_valid_line(file_obj.patch, line_num)
                            if nearest_line:
                                logger.warning(
                                    f"Issue at {file_name}:{line_num} is invalid, "
                                    f"adjusting to nearest valid line {nearest_line}"
                                )
                                issue_data["line"] = nearest_line
                            else:
                                invalid_lines.append(f"{file_name}:{line_num}")
                                logger.warning(
                                    f"Skipping issue at {file_name}:{line_num} - "
                                    "line not in diff, no nearby valid line found"
                                )
                                continue
                    
                    issues.append(CodeIssue(
                        file=issue_data["file"],
                        line=issue_data["line"],
                        end_line=issue_data.get("end_line"),
                        severity=IssueSeverity(issue_data["severity"]),
                        type=IssueType(issue_data["type"]),
                        description=issue_data["description"],
                        suggestion=issue_data.get("suggestion"),
                        original_code=issue_data.get("original_code"),
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse issue: {e}, data: {issue_data}")
                    continue
            
            if invalid_lines:
                logger.info(f"Filtered out {len(invalid_lines)} issues with invalid line numbers")
            
            # Parse approval recommendation
            rec_str = result.get("approval_recommendation", "COMMENT").upper()
            try:
                approval_rec = ReviewEvent(rec_str)
            except ValueError:
                approval_rec = ReviewEvent.COMMENT
            
            # Count critical issues
            critical_count = sum(
                1 for i in issues 
                if i.severity in (IssueSeverity.CRITICAL, IssueSeverity.HIGH)
            )
            
            return ReviewAnalysis(
                issues=issues,
                summary=result.get("summary", "Review completed."),
                approval_recommendation=approval_rec,
                files_reviewed=len(reviewable_files),
                total_issues=len(issues),
                critical_issues=critical_count,
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return ReviewAnalysis(
                issues=[],
                summary=f"Failed to parse review response: {e}",
                approval_recommendation=ReviewEvent.COMMENT,
                files_reviewed=len(reviewable_files),
                total_issues=0,
                critical_issues=0,
            )
        except Exception as e:
            logger.error(f"Azure OpenAI API error: {e}")
            raise
    
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
