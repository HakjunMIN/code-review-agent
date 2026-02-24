import logging
from fnmatch import fnmatch
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

class AzureSearchService:
    """Service for retrieving code standards from Azure AI Search."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.endpoint = settings.azure_ai_search_endpoint
        self._credential = None
        self._embedding_client: AzureOpenAI | None = None

    @property
    def credential(self):
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        return self._credential

    @property
    def embedding_client(self) -> AzureOpenAI:
        if self._embedding_client is None:
            token_provider = get_bearer_token_provider(
                self.credential,
                "https://cognitiveservices.azure.com/.default",
            )
            self._embedding_client = AzureOpenAI(
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_version=self.settings.azure_openai_api_version,
                azure_ad_token_provider=token_provider,
            )
        return self._embedding_client

    def _embed_query(self, query: str) -> list[float]:
        response = self.embedding_client.embeddings.create(
            model=self.settings.azure_openai_embedding_deployment,
            input=[query],
        )
        return response.data[0].embedding

    async def search_index(
        self,
        index_name: str,
        query: str,
        top_k: int,
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search a single index and return raw documents."""
        if not self.endpoint:
            return []

        try:
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )
            query_vector = self._embed_query(query)
            vector_query = VectorizedQuery(
                vector=query_vector,
                fields="content_vector",
                k=max(top_k, self.settings.azure_ai_search_semantic_top_k),
            )
            results = search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                filter=filter_expression,
                top=max(top_k, self.settings.azure_ai_search_semantic_top_k),
                query_type="semantic",
                semantic_configuration_name="standards-semantic-config",
            )
            return [dict(r) for r in results]
        except Exception as e:
            logger.warning(f"Azure AI Search query failed for index {index_name}: {e}")
            return []

    def _matches_changed_files(self, doc: dict[str, Any], changed_files: list[str]) -> bool:
        if not changed_files:
            return False

        direct_files = [f for f in (doc.get("affected_files") or []) if isinstance(f, str)]
        globs = [g for g in (doc.get("applies_to_globs") or []) if isinstance(g, str)]

        for changed_file in changed_files:
            if changed_file in direct_files:
                return True
            if any(fnmatch(changed_file, pattern) for pattern in globs):
                return True

        return False

    def _build_filter_expression(self, changed_files: list[str]) -> str:
        always_filter = "(standard_type eq 'corporate' or standard_type eq 'team' or standard_type eq 'repository')"
        if not changed_files:
            return always_filter

        file_filters = " or ".join([f"affected_files/any(f: f eq '{file_path}')" for file_path in changed_files])
        conditional_filter = (
            "((standard_type eq 'file_history' or standard_type eq 'postmortem') "
            f"and ({file_filters}))"
        )
        return f"({always_filter} or {conditional_filter})"

    def _filter_documents(self, docs: list[dict[str, Any]], changed_files: list[str]) -> list[dict[str, Any]]:
        filtered_docs: list[dict[str, Any]] = []
        for doc in docs:
            standard_type = str(doc.get("standard_type", "")).strip().lower()
            if standard_type in {"corporate", "team", "repository"}:
                filtered_docs.append(doc)
                continue
            if standard_type in {"file_history", "postmortem"} and self._matches_changed_files(doc, changed_files):
                filtered_docs.append(doc)
        return filtered_docs

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

    def _collect_standard_types(self, docs: list[dict[str, Any]]) -> list[str]:
        types: list[str] = []
        for doc in docs:
            standard_type = str(doc.get("standard_type", "")).strip().lower()
            if standard_type and standard_type not in types:
                types.append(standard_type)
        return types

    async def build_rag_context(self, query: str, changed_files: list[str]) -> tuple[str, list[str]]:
        """Build a combined RAG context from configured indices."""
        if not self.endpoint:
            return "", []

        sections: list[str] = []
        if not self.settings.azure_ai_search_standards_index:
            return "", []

        filter_expression = self._build_filter_expression(changed_files)
        docs = await self.search_index(
            self.settings.azure_ai_search_standards_index,
            query,
            self.settings.azure_ai_search_top_k,
            filter_expression=filter_expression,
        )
        filtered_docs = self._filter_documents(docs, changed_files)

        if not filtered_docs:
            return "", []

        referenced_docs = filtered_docs[: self.settings.azure_ai_search_top_k]
        referenced_types = self._collect_standard_types(referenced_docs)

        sections.append(f"### 코드 표준 ({self.settings.azure_ai_search_standards_index})")
        for doc in referenced_docs:
            sections.append(self._format_doc(doc, self.settings.azure_ai_search_max_chars))

        return "\n\n".join(sections), referenced_types
