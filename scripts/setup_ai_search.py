#!/usr/bin/env python
"""Setup Azure AI Search service, indexes, and sample documents."""
import subprocess
import json
import sys
import os
from datetime import datetime

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex, SimpleField, SearchableField, SearchFieldDataType
from azure.search.documents import SearchClient

# Configuration from environment variables
SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")
RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP")
LOCATION = os.getenv("AZURE_LOCATION")
SEARCH_SERVICE_NAME = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME") or f"aisdlcsearch{datetime.now().strftime('%m%d%H%M')}"
API_VERSION = "2023-11-01"

# Index definitions
INDEXES = [
    "corporate-standards-index",
    "project-standards-index",
    "incident-standards-index",
]

INDEX_SCHEMA = {
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True, "sortable": True},
        {"name": "title", "type": "Edm.String", "searchable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {"name": "code_sample", "type": "Edm.String", "searchable": True},
        {"name": "doc_type", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "tags", "type": "Collection(Edm.String)", "searchable": True, "filterable": True, "facetable": True},
    ]
}

# Sample documents
SAMPLE_DOCS = {
    "corporate-standards-index": {
        "id": "corp-001",
        "title": "전사 표준: 입력 검증 및 에러 처리",
        "content": "모든 외부 입력은 스키마 검증을 거쳐야 하며, 에러는 표준 에러 응답 포맷으로 반환한다. 예외는 로깅하고 내부 정보를 노출하지 않는다.",
        "code_sample": """def handle_request(payload: dict) -> dict:
    data = validate_payload(payload)
    try:
        return process(data)
    except Exception as exc:
        logger.exception("processing failed")
        return {"error": "internal_error"}""",
        "doc_type": "corporate",
        "tags": ["validation", "error-handling", "logging"],
    },
    "project-standards-index": {
        "id": "proj-001",
        "title": "프로젝트 표준: 비동기 HTTP 호출",
        "content": "외부 API 호출은 타임아웃과 재시도를 반드시 지정하며, 재시도 횟수는 최대 3회로 제한한다.",
        "code_sample": """async with httpx.AsyncClient(timeout=10) as client:
    for attempt in range(3):
        try:
            return await client.get(url)
        except httpx.TimeoutException:
            if attempt == 2:
                raise""",
        "doc_type": "project",
        "tags": ["httpx", "timeout", "retry"],
    },
    "incident-standards-index": {
        "id": "inc-001",
        "title": "인시던트 후 표준: 민감정보 마스킹",
        "content": "로그에는 토큰, 비밀번호, 개인정보를 남기지 않는다. 필요 시 마스킹 유틸을 사용한다.",
        "code_sample": """def mask_secret(value: str) -> str:
    if not value:
        return value
    return value[:2] + "***" + value[-2:]""",
        "doc_type": "incident",
        "tags": ["logging", "pii", "masking"],
    },
}


def run_az(args: list[str]) -> str:
    """Run Azure CLI command and return output."""
    result = subprocess.run(["az"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def create_index(index_client: SearchIndexClient, index_name: str):
    """Create a search index using SDK."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="code_sample", type=SearchFieldDataType.String),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="tags", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True, facetable=True),
    ]
    index = SearchIndex(name=index_name, fields=fields)
    
    try:
        index_client.create_or_update_index(index)
        print(f"✅ Index created: {index_name}")
    except Exception as e:
        print(f"❌ Failed to create index {index_name}: {e}")
        raise


def index_document(endpoint: str, credential, index_name: str, doc: dict):
    """Index a document using SDK."""
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
    
    try:
        result = search_client.upload_documents(documents=[doc])
        if result[0].succeeded:
            print(f"✅ Document indexed in {index_name}: {doc['id']}")
        else:
            print(f"❌ Failed to index document: {result[0].error_message}")
    except Exception as e:
        print(f"❌ Failed to index document: {e}")
        raise


def main():
    print("=" * 60)
    print("Azure AI Search Setup Script")
    print("=" * 60)
    
    # Set subscription
    print(f"\n🔄 Setting subscription to {SUBSCRIPTION_ID}...")
    run_az(["account", "set", "--subscription", SUBSCRIPTION_ID])
    
    # Create resource group if not exists
    print(f"\n🔄 Ensuring resource group {RESOURCE_GROUP} exists...")
    run_az(["group", "create", "-n", RESOURCE_GROUP, "-l", LOCATION])
    print(f"✅ Resource group ready: {RESOURCE_GROUP}")
    
    # Check if search service exists
    print(f"\n🔄 Checking search service {SEARCH_SERVICE_NAME}...")
    try:
        run_az([
            "search", "service", "show",
            "-g", RESOURCE_GROUP,
            "-n", SEARCH_SERVICE_NAME
        ])
        print(f"✅ Search service exists: {SEARCH_SERVICE_NAME}")
    except RuntimeError:
        print(f"🔄 Creating search service {SEARCH_SERVICE_NAME}...")
        run_az([
            "search", "service", "create",
            "-g", RESOURCE_GROUP,
            "-n", SEARCH_SERVICE_NAME,
            "-l", LOCATION,
            "--sku", "basic",
            "--partition-count", "1",
            "--replica-count", "1"
        ])
        print(f"✅ Search service created: {SEARCH_SERVICE_NAME}")
    
    # Initialize credential and clients
    print("\n🔄 Initializing Azure credential...")
    credential = DefaultAzureCredential()
    endpoint = f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    print(f"✅ Credential initialized")
    
    # Create indexes
    print("\n🔄 Creating indexes...")
    for index_name in INDEXES:
        create_index(index_client, index_name)
    
    # Index sample documents
    print("\n🔄 Indexing sample documents...")
    for index_name, doc in SAMPLE_DOCS.items():
        index_document(endpoint, credential, index_name, doc)
    
    # Output configuration
    print("\n" + "=" * 60)
    print("Setup Complete! Add these to your .env file:")
    print("=" * 60)
    print(f"AZURE_AI_SEARCH_ENDPOINT={endpoint}")
    print(f"AZURE_AI_SEARCH_CORPORATE_INDEX=corporate-standards-index")
    print(f"AZURE_AI_SEARCH_PROJECT_INDEX=project-standards-index")
    print(f"AZURE_AI_SEARCH_INCIDENT_INDEX=incident-standards-index")
    print("\n# Note: Using DefaultAzureCredential, no API key needed")
    
    # Return values for programmatic use
    return {
        "endpoint": endpoint,
        "indexes": INDEXES,
    }


if __name__ == "__main__":
    main()
