from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Azure OpenAI Configuration
    azure_openai_endpoint: str
    azure_openai_api_key: str | None = None  # Optional, uses Azure AD if not provided
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-10-21"

    # Azure AI Search (RAG) Configuration - uses DefaultAzureCredential
    azure_ai_search_endpoint: str | None = None
    azure_ai_search_corporate_index: str | None = None
    azure_ai_search_project_index: str | None = None
    azure_ai_search_incident_index: str | None = None
    azure_ai_search_top_k: int = 5
    azure_ai_search_max_chars: int = 2000
    azure_ai_search_enabled: bool = True
    
    # Optional default GitHub PAT
    github_pat: str | None = None
    
    # Application settings
    max_files_per_review: int = 50
    max_file_size_kb: int = 500
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
