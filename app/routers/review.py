from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models.schemas import ReviewRequest, ReviewResponse
from app.services.review_service import ReviewService


router = APIRouter(prefix="/api/v1", tags=["review"])


@router.post("/review", response_model=ReviewResponse)
async def review_pr(
    request: ReviewRequest,
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    """
    Review a GitHub Pull Request.
    
    This endpoint accepts a GitHub PR URL and a Personal Access Token,
    performs an AI-powered code review, and posts the results as comments
    on the PR.
    
    Args:
        request: ReviewRequest containing:
            - pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)
            - github_pat: GitHub Personal Access Token with repo access
    
    Returns:
        ReviewResponse containing:
            - success: Whether the review completed successfully
            - pr_url: The reviewed PR URL
            - review_id: GitHub review ID (if posted)
            - analysis: Detailed analysis results
            - message: Status message
            - errors: Any errors encountered
    """
    review_service = ReviewService(settings)
    result = await review_service.review_pr(request)
    
    if not result.success:
        raise HTTPException(
            status_code=400 if "Invalid" in result.message else 500,
            detail=result.message,
        )
    
    return result


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "code-review-agent"}
