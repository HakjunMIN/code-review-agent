import asyncio
import logging
from typing import Any

import httpx

from app.config import Settings
from app.models.schemas import (
    ReviewAnalysis,
    ReviewComment,
    ReviewEvent,
    ReviewRequest,
    ReviewResponse,
)
from app.services.azure_openai_service import AzureOpenAIService
from app.services.azure_search_service import AzureSearchService
from app.services.github_service import GitHubService

logger = logging.getLogger(__name__)


class ReviewService:
    """Orchestration service for PR code review workflow."""

    def __init__(self, settings: Settings):
        """Initialize review service with settings."""
        self.settings = settings
        self.openai_service = AzureOpenAIService(settings)

    async def review_pr(self, request: ReviewRequest) -> ReviewResponse:
        """
        Perform a complete code review on a PR.

        This method orchestrates the entire review workflow:
        1. Parse PR URL and fetch PR details
        2. Get list of changed files
        3. Fetch file contents for context
        4. Analyze code with Azure OpenAI
        5. Post review and inline comments to GitHub

        Args:
            request: ReviewRequest with PR URL and GitHub PAT

        Returns:
            ReviewResponse with analysis results
        """
        errors: list[str] = []
        pr_url = str(request.pr_url)

        try:
            # Step 1: Parse PR URL
            owner, repo, pr_number = GitHubService.parse_pr_url(pr_url)
            logger.info(f"Reviewing PR: {owner}/{repo}#{pr_number}")

            # Initialize GitHub service with PAT
            github_service = GitHubService(request.github_pat)

            # Step 2: Fetch PR details
            pr_details = await github_service.get_pr_details(owner, repo, pr_number)
            logger.info(f"PR Title: {pr_details.title}")

            # Step 3: Get changed files
            files = await github_service.get_pr_files(owner, repo, pr_number)
            logger.info(f"Found {len(files)} changed files")

            # Filter files by size limit
            reviewable_files = [
                f for f in files
                if f.changes <= self.settings.max_file_size_kb * 10  # rough estimate
            ][:self.settings.max_files_per_review]

            if len(reviewable_files) < len(files):
                errors.append(
                    f"Only reviewing {len(reviewable_files)} of {len(files)} files "
                    f"(limited by max_files_per_review or file size)"
                )

            # Step 4: Fetch file contents for context
            file_contents: dict[str, str | None] = {}
            fetch_tasks = []

            for file in reviewable_files:
                if file.status != "removed":
                    fetch_tasks.append(
                        self._fetch_file_content(
                            github_service, owner, repo,
                            file.filename, pr_details.head_sha
                        )
                    )

            if fetch_tasks:
                results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, tuple):
                        filename, content = result
                        file_contents[filename] = content
                    elif isinstance(result, Exception):
                        logger.warning(f"Failed to fetch file content: {result}")

            # Step 5: Analyze code with Azure OpenAI
            rag_context = await self._build_rag_context(
                pr_title=pr_details.title,
                pr_body=pr_details.body,
                files=reviewable_files,
            )
            rag_context_text = rag_context["context"]
            referenced_standard_types = rag_context["standard_types"]
            rag_referenced = bool(rag_context_text and rag_context_text.strip())
            analysis = await self.openai_service.analyze_code(
                pr_title=pr_details.title,
                pr_body=pr_details.body,
                files=reviewable_files,
                file_contents=file_contents,
                rag_context=rag_context_text,
            )

            logger.info(
                f"Analysis complete: {analysis.total_issues} issues found, "
                f"recommendation: {analysis.approval_recommendation.value}"
            )

            # Step 6: Post review to GitHub
            review_id = await self._post_review(
                github_service=github_service,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_id=pr_details.head_sha,
                analysis=analysis,
                rag_referenced=rag_referenced,
                referenced_standard_types=referenced_standard_types,
            )

            return ReviewResponse(
                success=True,
                pr_url=pr_url,
                review_id=review_id,
                analysis=analysis,
                message=f"Review completed successfully. Found {analysis.total_issues} issues.",
                errors=errors,
            )

        except ValueError as e:
            logger.error(f"Invalid request: {e}")
            return ReviewResponse(
                success=False,
                pr_url=pr_url,
                message=str(e),
                errors=[str(e)],
            )
        except Exception as e:
            logger.exception(f"Review failed: {e}")
            return ReviewResponse(
                success=False,
                pr_url=pr_url,
                message=f"Review failed: {str(e)}",
                errors=[str(e)] + errors,
            )

    async def _fetch_file_content(
        self,
        github_service: GitHubService,
        owner: str,
        repo: str,
        filename: str,
        ref: str
    ) -> tuple[str, str | None]:
        """Fetch file content and return as tuple with filename."""
        content = await github_service.get_file_content(owner, repo, filename, ref)
        return (filename, content)

    async def _post_review(
        self,
        github_service: GitHubService,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        analysis: ReviewAnalysis,
        rag_referenced: bool = False,
        referenced_standard_types: list[str] | None = None,
    ) -> int | None:
        """
        Post review with inline comments to GitHub.

        Args:
            github_service: GitHub API service
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_id: Commit SHA to review
            analysis: Analysis results

        Returns:
            Review ID if successful
        """
        # Build inline comments for each issue
        inline_comments: list[ReviewComment] = []

        for issue in analysis.issues:
            comment_body = self.openai_service.format_issue_as_github_comment(issue)
            inline_comments.append(ReviewComment(
                path=issue.file,
                line=issue.line,
                side="RIGHT",
                body=comment_body,
            ))

        # Build review summary
        review_body = self.openai_service.format_review_summary(
            analysis,
            rag_referenced=rag_referenced,
            referenced_standard_types=referenced_standard_types,
        )

        try:
            # Try to create review with inline comments
            if inline_comments:
                try:
                    response = await github_service.create_review(
                        owner=owner,
                        repo=repo,
                        pr_number=pr_number,
                        commit_id=commit_id,
                        body=review_body,
                        event=analysis.approval_recommendation,
                        comments=inline_comments[:50],  # GitHub limits to ~50 comments per review
                    )

                    review_id = response.get("id")
                    logger.info(f"Posted review with ID: {review_id} and {len(inline_comments[:50])} inline comments")

                    # If there are more than 50 comments, post remaining as separate comments
                    if len(inline_comments) > 50:
                        for idx, comment in enumerate(inline_comments[50:], start=51):
                            try:
                                await github_service.create_review_comment(
                                    owner=owner,
                                    repo=repo,
                                    pr_number=pr_number,
                                    commit_id=commit_id,
                                    path=comment.path,
                                    line=comment.line,
                                    body=comment.body,
                                    side=comment.side,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to post comment #{idx}: {e}")

                    return review_id

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 422:
                        response_text = e.response.text[:500]

                        # Check if this is an "own pull request" error
                        if "own pull request" in response_text.lower():
                            logger.warning(
                                f"Cannot use {analysis.approval_recommendation.value} on own PR. "
                                "Falling back to COMMENT event."
                            )
                            # Retry with COMMENT event (allowed on own PRs)
                            response = await github_service.create_review(
                                owner=owner,
                                repo=repo,
                                pr_number=pr_number,
                                commit_id=commit_id,
                                body=review_body,
                                event=ReviewEvent.COMMENT,
                                comments=inline_comments[:50],
                            )
                            review_id = response.get("id")
                            logger.info(f"Posted review with COMMENT event, ID: {review_id}")
                            return review_id

                        # 422 error: inline comments likely have invalid line numbers
                        logger.warning(
                            f"Failed to post inline comments (422 error): {response_text}. "
                            "Falling back to review without inline comments."
                        )
                        # Retry without inline comments
                        response = await github_service.create_review(
                            owner=owner,
                            repo=repo,
                            pr_number=pr_number,
                            commit_id=commit_id,
                            body=review_body,
                            event=analysis.approval_recommendation,
                            comments=None,
                        )
                        review_id = response.get("id")
                        logger.info(f"Posted review without inline comments, ID: {review_id}")
                        return review_id
                    else:
                        raise
            else:
                # No inline comments, just post review
                try:
                    response = await github_service.create_review(
                        owner=owner,
                        repo=repo,
                        pr_number=pr_number,
                        commit_id=commit_id,
                        body=review_body,
                        event=analysis.approval_recommendation,
                        comments=None,
                    )
                    review_id = response.get("id")
                    logger.info(f"Posted review without inline comments, ID: {review_id}")
                    return review_id
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 422 and "own pull request" in e.response.text.lower():
                        logger.warning(
                            f"Cannot use {analysis.approval_recommendation.value} on own PR. "
                            "Falling back to COMMENT event."
                        )
                        response = await github_service.create_review(
                            owner=owner,
                            repo=repo,
                            pr_number=pr_number,
                            commit_id=commit_id,
                            body=review_body,
                            event=ReviewEvent.COMMENT,
                            comments=None,
                        )
                        review_id = response.get("id")
                        logger.info(f"Posted review with COMMENT event, ID: {review_id}")
                        return review_id
                    raise

        except Exception as e:
            logger.error(f"Failed to post review: {e}", exc_info=True)
            # Fallback: post as a simple issue comment
            try:
                await github_service.create_issue_comment(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    body=review_body,
                )
                logger.info("Posted review as issue comment (fallback)")
            except Exception as fallback_error:
                logger.error(f"Fallback comment also failed: {fallback_error}")

            return None

    def _build_search_query(
        self,
        pr_title: str,
        pr_body: str | None,
        files: list[Any],
    ) -> str:
        parts: list[str] = [pr_title]
        if pr_body:
            parts.append(pr_body)

        file_names = " ".join([f.filename for f in files])
        if file_names:
            parts.append(file_names)

        # Add a small sample of added lines to improve retrieval relevance
        added_lines: list[str] = []
        for file in files:
            if not getattr(file, "patch", None):
                continue
            for line in str(file.patch).split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:].strip())
                    if len(added_lines) >= 50:
                        break
            if len(added_lines) >= 50:
                break

        if added_lines:
            parts.append(" ".join(added_lines))

        query = "\n".join([p for p in parts if p]).strip()
        return query[:2000]

    async def _build_rag_context(
        self,
        pr_title: str,
        pr_body: str | None,
        files: list[Any],
    ) -> dict[str, str | list[str] | None]:
        if not self.settings.azure_ai_search_enabled:
            return {"context": None, "standard_types": []}

        if not self.settings.azure_ai_search_endpoint:
            return {"context": None, "standard_types": []}

        if not self.settings.azure_ai_search_standards_index:
            return {"context": None, "standard_types": []}

        query = self._build_search_query(pr_title, pr_body, files)
        changed_files = [str(f.filename) for f in files if getattr(f, "filename", None)]
        search_service = AzureSearchService(self.settings)
        rag_context, referenced_standard_types = await search_service.build_rag_context(query, changed_files)
        return {
            "context": rag_context or None,
            "standard_types": referenced_standard_types,
        }
