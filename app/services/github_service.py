import base64
import re
from typing import Any

import httpx

from app.models.schemas import (
    PRDetails,
    PRFile,
    ReviewComment,
    ReviewEvent,
)


class GitHubService:
    """Service for interacting with GitHub API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, pat: str):
        """Initialize GitHub service with Personal Access Token."""
        self.pat = pat
        self.headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
        """
        Parse a GitHub PR URL to extract owner, repo, and PR number.

        Args:
            pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)

        Returns:
            Tuple of (owner, repo, pr_number)

        Raises:
            ValueError: If URL format is invalid
        """
        pattern = r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
        match = re.match(pattern, str(pr_url))
        if not match:
            raise ValueError(f"Invalid GitHub PR URL format: {pr_url}")
        return match.group(1), match.group(2), int(match.group(3))

    async def get_pr_details(self, owner: str, repo: str, pr_number: int) -> PRDetails:
        """
        Fetch PR details from GitHub API.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            PRDetails object with PR information
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

        return PRDetails(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            user=data["user"]["login"],
            html_url=data["html_url"],
        )

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[PRFile]:
        """
        Fetch list of files changed in a PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of PRFile objects
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        files = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params={"page": page, "per_page": 100},
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for file_data in data:
                    files.append(
                        PRFile(
                            filename=file_data["filename"],
                            status=file_data["status"],
                            additions=file_data.get("additions", 0),
                            deletions=file_data.get("deletions", 0),
                            changes=file_data.get("changes", 0),
                            patch=file_data.get("patch"),
                            contents_url=file_data.get("contents_url"),
                            sha=file_data.get("sha"),
                        )
                    )

                page += 1
                if len(data) < 100:
                    break

        return files

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        """
        Fetch content of a file at a specific ref.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Git ref (commit SHA, branch, or tag)

        Returns:
            File content as string, or None if file not found
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                params={"ref": ref},
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")

        return data.get("content")

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """
        Fetch the unified diff for a PR.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            Unified diff as string
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {**self.headers, "Accept": "application/vnd.github.diff"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        body: str,
        event: ReviewEvent,
        comments: list[ReviewComment] | None = None,
    ) -> dict[str, Any]:
        """
        Create a review on a PR with optional inline comments.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_id: The SHA of the commit to review
            body: Review body text
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            comments: Optional list of inline comments

        Returns:
            GitHub API response
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": event.value,
        }

        if comments:
            payload["comments"] = [
                {
                    "path": c.path,
                    "line": c.line,
                    "side": c.side,
                    "body": c.body,
                }
                for c in comments
            ]

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def create_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
    ) -> dict[str, Any]:
        """
        Create a single review comment on a specific line.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_id: The SHA of the commit
            path: File path
            line: Line number
            body: Comment body
            side: Side of the diff (LEFT or RIGHT)

        Returns:
            GitHub API response
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/comments"

        payload = {
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
            "body": body,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def create_issue_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> dict[str, Any]:
        """
        Create a general comment on a PR (not inline).

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number (same as issue number)
            body: Comment body

        Returns:
            GitHub API response
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{pr_number}/comments"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json={"body": body})
            response.raise_for_status()
            return response.json()
