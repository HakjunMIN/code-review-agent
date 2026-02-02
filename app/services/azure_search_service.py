import logging
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from app.config import Settings


logger = logging.getLogger(__name__)



class AzureSearchService:
    """Service for retrieving code standards from Azure AI Search."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.endpoint = settings.azure_ai_search_endpoint
        self._credential = None

    @property
    def credential(self):
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        return self._credential

    async def search_index(self, index_name: str, query: str, top_k: int) -> list[dict[str, Any]]:
        """Search a single index and return raw documents."""
        if not self.endpoint:
            return []

        try:
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )
            results = search_client.search(search_text=query, top=top_k)
            return [dict(r) for r in results]
        except Exception as e:
            logger.warning(f"Azure AI Search query failed for index {index_name}: {e}")
            return []

    def _extract_text_field(self, doc: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = doc.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _format_doc(self, doc: dict[str, Any], max_chars: int) -> str:
        title = self._extract_text_field(doc, ["title", "name", "id", "documentId"]) or "Untitled"
        content = (
            self._extract_text_field(doc, ["content", "text", "body", "summary", "description"]) or ""
        )
        code_sample = (
            self._extract_text_field(doc, ["code_sample", "code", "sample", "example"]) or ""
        )

        parts = [f"- Title: {title}"]
        if content:
            trimmed = content[:max_chars]
            parts.append(f"  Content: {trimmed}")
        if code_sample:
            trimmed_code = code_sample[:max_chars]
            parts.append("  Code Sample:\n" + trimmed_code)

        if len(parts) == 1:
            # Fallback to raw doc if no useful fields
            parts.append(f"  Raw: {str(doc)[:max_chars]}")

        return "\n".join(parts)

    async def build_rag_context(self, query: str) -> str:
        """Build a combined RAG context from configured indices."""
        if not self.endpoint:
            return ""

        sections: list[str] = []
        index_specs = [
            ("전사표준", self.settings.azure_ai_search_corporate_index),
            ("프로젝트표준", self.settings.azure_ai_search_project_index),
            ("인시던트 후 표준", self.settings.azure_ai_search_incident_index),
        ]

        for label, index_name in index_specs:
            if not index_name:
                continue
            docs = await self.search_index(index_name, query, self.settings.azure_ai_search_top_k)
            if not docs:
                continue

            sections.append(f"### {label} ({index_name})")
            for doc in docs:
                sections.append(self._format_doc(doc, self.settings.azure_ai_search_max_chars))

        return "\n\n".join(sections)
