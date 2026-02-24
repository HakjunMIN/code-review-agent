import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import review

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_settings()
    logger.info("Starting Code Review Agent...")
    logger.info(f"Azure OpenAI Endpoint: {settings.azure_openai_endpoint}")
    logger.info(f"Azure OpenAI Deployment: {settings.azure_openai_deployment}")
    yield
    # Shutdown
    logger.info("Shutting down Code Review Agent...")


app = FastAPI(
    title="Code Review Agent",
    description="""
    AI-powered Code Review Agent for GitHub Pull Requests.

    This service analyzes code changes in GitHub PRs using Azure OpenAI
    and automatically posts review comments with actionable feedback.

    ## Features
    - Automatic code analysis for bugs, security issues, and best practices
    - Inline comments on specific code lines
    - Severity-based issue categorization
    - GitHub suggestion blocks for easy fixes

    ## Usage
    1. POST your PR URL and GitHub PAT to `/api/v1/review`
    2. The agent will analyze the PR and post review comments
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(review.router)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Code Review Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
