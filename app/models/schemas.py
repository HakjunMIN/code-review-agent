from pydantic import BaseModel, Field, HttpUrl
from enum import Enum


class ReviewEvent(str, Enum):
    """GitHub review event types."""
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class IssueSeverity(str, Enum):
    """Severity level for code issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueType(str, Enum):
    """Type of code issue."""
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    BEST_PRACTICE = "best_practice"


# Request Models
class ReviewRequest(BaseModel):
    """Request model for PR review."""
    pr_url: HttpUrl = Field(..., description="GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)")
    github_pat: str = Field(..., description="GitHub Personal Access Token")


# GitHub API Response Models
class PRFile(BaseModel):
    """Model for a file changed in a PR."""
    filename: str
    status: str  # added, removed, modified, renamed
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: str | None = None
    contents_url: str | None = None
    sha: str | None = None


class PRDetails(BaseModel):
    """Model for PR details."""
    number: int
    title: str
    body: str | None = None
    state: str
    head_sha: str
    base_sha: str
    head_ref: str
    base_ref: str
    user: str
    html_url: str


# Code Review Models
class CodeIssue(BaseModel):
    """Model for a single code issue found during review."""
    file: str = Field(..., description="File path where the issue was found")
    line: int = Field(..., description="Line number where the issue occurs")
    end_line: int | None = Field(None, description="End line for multi-line issues")
    severity: IssueSeverity
    type: IssueType
    description: str = Field(..., description="Description of the issue")
    suggestion: str | None = Field(None, description="Suggested fix or corrected code")
    original_code: str | None = Field(None, description="Original problematic code snippet")


class FileReview(BaseModel):
    """Model for review of a single file."""
    filename: str
    issues: list[CodeIssue] = Field(default_factory=list)
    summary: str = Field(..., description="Summary of the file review")
    status: str = Field(..., description="Overall status: good, needs_attention, critical")


class ReviewAnalysis(BaseModel):
    """Complete analysis result from Azure OpenAI."""
    issues: list[CodeIssue] = Field(default_factory=list)
    summary: str = Field(..., description="Overall assessment of the PR")
    approval_recommendation: ReviewEvent = Field(
        default=ReviewEvent.COMMENT,
        description="Recommended review action"
    )
    files_reviewed: int = 0
    total_issues: int = 0
    critical_issues: int = 0


# GitHub Review Models
class ReviewComment(BaseModel):
    """Model for an inline review comment."""
    path: str = Field(..., description="File path")
    line: int = Field(..., description="Line number for the comment")
    side: str = Field(default="RIGHT", description="Side of the diff (LEFT or RIGHT)")
    body: str = Field(..., description="Comment body")


class CreateReviewRequest(BaseModel):
    """Model for creating a GitHub review."""
    commit_id: str
    body: str
    event: ReviewEvent
    comments: list[ReviewComment] = Field(default_factory=list)


# Response Models
class ReviewResponse(BaseModel):
    """Response model for PR review."""
    success: bool
    pr_url: str
    review_id: int | None = None
    analysis: ReviewAnalysis | None = None
    message: str
    errors: list[str] = Field(default_factory=list)
