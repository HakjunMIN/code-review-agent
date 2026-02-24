#!/usr/bin/env python
"""Create Azure AI Search index and ingest markdown standards with embeddings."""

import contextlib
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")
RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP")
LOCATION = os.getenv("AZURE_LOCATION", "koreacentral")
SEARCH_SERVICE_NAME = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME")
SEARCH_ENDPOINT = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
INDEX_NAME = os.getenv("AZURE_AI_SEARCH_STANDARDS_INDEX", "code-standards-index")

OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
STANDARDS_DIR = Path(os.getenv("STANDARDS_DOCS_PATH", "standards"))
EMBEDDING_DIMENSIONS = 1536

REQUIRED_FRONTMATTER_FIELDS = {
    "standard_id",
    "standard_type",
    "title",
    "applies_scope",
    "tags",
    "language",
    "updated_at",
    "repo",
}


@dataclass
class ParsedMarkdown:
    source_file: str
    metadata: dict[str, Any]
    content: str


def run_az(args: list[str]) -> str:
    """Run Azure CLI command and return output."""
    result = subprocess.run(["az"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def resolve_search_endpoint() -> str:
    if SEARCH_ENDPOINT:
        return SEARCH_ENDPOINT
    if SEARCH_SERVICE_NAME:
        return f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
    raise RuntimeError(
        "Set AZURE_AI_SEARCH_ENDPOINT or AZURE_AI_SEARCH_SERVICE_NAME before running this script."
    )


def ensure_search_service() -> str:
    endpoint = resolve_search_endpoint()
    if not SEARCH_SERVICE_NAME:
        return endpoint
    if not SUBSCRIPTION_ID or not RESOURCE_GROUP:
        return endpoint

    run_az(["account", "set", "--subscription", SUBSCRIPTION_ID])
    run_az(["group", "create", "-n", RESOURCE_GROUP, "-l", LOCATION])

    try:
        run_az(["search", "service", "show", "-g", RESOURCE_GROUP, "-n", SEARCH_SERVICE_NAME])
    except RuntimeError:
        run_az([
            "search",
            "service",
            "create",
            "-g",
            RESOURCE_GROUP,
            "-n",
            SEARCH_SERVICE_NAME,
            "-l",
            LOCATION,
            "--sku",
            "basic",
            "--partition-count",
            "1",
            "--replica-count",
            "1",
        ])

    return endpoint


def parse_frontmatter(raw_text: str, source_file: str) -> tuple[dict[str, Any], str]:
    """Parse yaml-like frontmatter with JSON-list support."""
    if not raw_text.startswith("---\n"):
        raise ValueError(f"{source_file}: frontmatter is required")

    parts = raw_text.split("\n---\n", 1)
    if len(parts) != 2:
        raise ValueError(f"{source_file}: invalid frontmatter block")

    frontmatter_raw, body = parts
    metadata: dict[str, Any] = {}

    for line in frontmatter_raw.splitlines()[1:]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"{source_file}: invalid frontmatter line '{line}'")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if value.startswith("[") and value.endswith("]"):
            metadata[key] = json.loads(value)
        elif value.lower() in {"true", "false"}:
            metadata[key] = value.lower() == "true"
        elif value.startswith('"') and value.endswith('"'):
            metadata[key] = value[1:-1]
        else:
            metadata[key] = value

    missing = REQUIRED_FRONTMATTER_FIELDS - set(metadata.keys())
    if missing:
        raise ValueError(f"{source_file}: missing frontmatter fields {sorted(missing)}")

    metadata.setdefault("applies_to_globs", [])
    metadata.setdefault("affected_files", [])
    metadata.setdefault("team", "")
    metadata.setdefault("severity", "medium")
    metadata.setdefault("postmortem_id", "")
    metadata.setdefault("related_paths", [])

    return metadata, body.strip()


def load_markdown_documents(root_dir: Path) -> list[ParsedMarkdown]:
    if not root_dir.exists():
        raise FileNotFoundError(f"Standards directory not found: {root_dir}")

    docs: list[ParsedMarkdown] = []
    for file_path in sorted(root_dir.rglob("*.md")):
        raw_text = file_path.read_text(encoding="utf-8")
        metadata, content = parse_frontmatter(raw_text, str(file_path))
        docs.append(
            ParsedMarkdown(
                source_file=str(file_path).replace("\\", "/"),
                metadata=metadata,
                content=content,
            )
        )
    return docs


def chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    """Chunk markdown by heading and max length."""
    blocks = re.split(r"\n(?=##?\s)", text)
    chunks: list[str] = []
    current = ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if len(current) + len(block) + 2 <= max_chars:
            current = f"{current}\n\n{block}".strip()
            continue

        if current:
            chunks.append(current)
        if len(block) <= max_chars:
            current = block
        else:
            for i in range(0, len(block), max_chars):
                chunks.append(block[i : i + max_chars])
            current = ""

    if current:
        chunks.append(current)

    return chunks


def create_embedding_client() -> AzureOpenAI:
    if not OPENAI_ENDPOINT:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is required for embeddings")

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        api_version=OPENAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )


def embed_texts(client: AzureOpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_DEPLOYMENT,
        input=texts,
    )
    return [item.embedding for item in response.data]


def create_index(index_client: SearchIndexClient) -> None:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
        SimpleField(name="standard_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="standard_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="applies_scope", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="source_file", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="repo", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="team", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="language", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="severity", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="updated_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="postmortem_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="tags",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="applies_to_globs",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="affected_files",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="related_paths",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="standards-vector-profile",
        ),
    ]

    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(name="standards-hnsw")
            ],
            profiles=[
                VectorSearchProfile(
                    name="standards-vector-profile",
                    algorithm_configuration_name="standards-hnsw",
                )
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="standards-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ]
        ),
    )
    with contextlib.suppress(Exception):
        index_client.delete_index(INDEX_NAME)

    index_client.create_or_update_index(index)


def build_documents(parsed_docs: list[ParsedMarkdown], embedding_client: AzureOpenAI) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for parsed_doc in parsed_docs:
        chunks = chunk_text(parsed_doc.content)
        if not chunks:
            continue

        embeddings = embed_texts(embedding_client, chunks)
        metadata = parsed_doc.metadata

        for idx, chunk in enumerate(chunks):
            chunk_key = f"{metadata['standard_id']}-{idx + 1}"
            doc_id = hashlib.sha1(chunk_key.encode("utf-8")).hexdigest()

            documents.append(
                {
                    "id": doc_id,
                    "standard_id": str(metadata["standard_id"]),
                    "standard_type": str(metadata["standard_type"]),
                    "applies_scope": str(metadata["applies_scope"]),
                    "source_file": parsed_doc.source_file,
                    "title": str(metadata["title"]),
                    "content": chunk,
                    "tags": list(metadata.get("tags", [])),
                    "applies_to_globs": list(metadata.get("applies_to_globs", [])),
                    "affected_files": list(metadata.get("affected_files", [])),
                    "related_paths": list(metadata.get("related_paths", [])),
                    "repo": str(metadata.get("repo", "")),
                    "team": str(metadata.get("team", "")),
                    "language": str(metadata.get("language", "all")),
                    "severity": str(metadata.get("severity", "medium")),
                    "postmortem_id": str(metadata.get("postmortem_id", "")),
                    "updated_at": str(metadata.get("updated_at", datetime.datetime.now(datetime.UTC).date())),
                    "content_vector": embeddings[idx],
                }
            )

    return documents


def upload_documents(search_client: SearchClient, documents: list[dict[str, Any]]) -> None:
    batch_size = 50
    uploaded = 0
    for i in range(0, len(documents), batch_size):
        chunk = documents[i : i + batch_size]
        result = search_client.upload_documents(documents=chunk)
        for r in result:
            if not r.succeeded:
                raise RuntimeError(f"Failed to upload document: {r.key} - {r.error_message}")
        uploaded += len(chunk)
    print(f"✅ Uploaded {uploaded} documents into {INDEX_NAME}")


def main() -> None:
    print("=" * 70)
    print("Azure AI Search Standards Index Setup")
    print("=" * 70)

    endpoint = ensure_search_service()
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    search_client = SearchClient(endpoint=endpoint, index_name=INDEX_NAME, credential=credential)
    embedding_client = create_embedding_client()

    print("🔄 Creating/Updating index schema...")
    create_index(index_client)
    print(f"✅ Index ready: {INDEX_NAME}")

    print(f"🔄 Loading markdown standards from {STANDARDS_DIR}...")
    parsed_docs = load_markdown_documents(STANDARDS_DIR)
    print(f"✅ Loaded {len(parsed_docs)} markdown files")

    print("🔄 Building chunked documents with embeddings...")
    documents = build_documents(parsed_docs, embedding_client)
    if not documents:
        raise RuntimeError("No documents generated for indexing")
    print(f"✅ Generated {len(documents)} chunk documents")

    print("🔄 Uploading documents to Azure AI Search...")
    upload_documents(search_client, documents)

    print("\n" + "=" * 70)
    print("Setup complete. Configure .env with:")
    print("=" * 70)
    print(f"AZURE_AI_SEARCH_ENDPOINT={endpoint}")
    print(f"AZURE_AI_SEARCH_STANDARDS_INDEX={INDEX_NAME}")
    print(f"AZURE_OPENAI_EMBEDDING_DEPLOYMENT={OPENAI_EMBEDDING_DEPLOYMENT}")
    print("STANDARDS_DOCS_PATH=standards")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"❌ Setup failed: {error}", file=sys.stderr)
        sys.exit(1)
