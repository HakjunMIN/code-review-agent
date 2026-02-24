# Code Review Agent

AI-powered Code Review Agent for GitHub Pull Requests using Azure OpenAI.

## Features

- 🔍 **Automatic PR Analysis**: Analyzes code changes in GitHub Pull Requests
- 🤖 **AI-Powered Reviews**: Uses Azure OpenAI (Codex model recommended) for intelligent code review
- 📚 **RAG with Azure AI Search**: Grounds reviews in coding standards by type (`corporate`, `team`, `repository`, `file_history`, `postmortem`)
- 💬 **Inline Comments**: Posts review comments directly on specific code lines
- 🎯 **Issue Categorization**: Categorizes issues by type (bug, security, performance, style)
- ⚠️ **Severity Levels**: Rates issues from critical to info
- 💡 **Actionable Suggestions**: Provides code suggestions using GitHub suggestion blocks
- ✅ **Review Decisions**: Recommends APPROVE, REQUEST_CHANGES, or COMMENT

### RAG-Based Review Flow

1. **PR Ingestion**: Fetch PR details, changed files, and diffs from GitHub
2. **RAG Retrieval**: Query Azure AI Search indexes for relevant coding standards
   - Corporate standards (company-wide rules)
   - Project standards (project-specific conventions)
   - Incident standards (lessons learned from past incidents)
3. **Context Building**: Combine PR changes with retrieved standards
4. **AI Analysis**: Azure OpenAI analyzes code against standards and best practices
5. **Review Posting**: Post inline comments and summary to GitHub PR

## Prerequisites

- Python 3.11+
- Azure OpenAI deployment (Codex model recommended, e.g. `gpt-5.2-codex`)
- Azure AI Search service (optional, for RAG-based reviews)
- GitHub Personal Access Token (PAT) with `repo` scope
- Azure CLI (for authentication): `az login`

## Installation

1. **Clone the repository**

```bash
git clone https://github.com/HakjunMIN/code-review-agent.git
cd code-review-agent
```

2. **Install dependencies with uv**

```bash
uv sync
```

3. **Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` with your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-5.2-codex
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Azure AI Search (RAG) - uses DefaultAzureCredential (az login)
AZURE_AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_AI_SEARCH_STANDARDS_INDEX=code-standards-index
AZURE_AI_SEARCH_TOP_K=5
AZURE_AI_SEARCH_SEMANTIC_TOP_K=12
AZURE_AI_SEARCH_MAX_CHARS=2000
AZURE_AI_SEARCH_ENABLED=true
STANDARDS_DOCS_PATH=standards
```

## Azure AI Search Setup (Optional - for RAG)

### Prerequisites

1. **Azure CLI Authentication**

```bash
az login
az account set --subscription <your-subscription-id>
```

2. **Run Setup Script**

The setup script will:
- Create Azure AI Search service (if not exists)
- Create a single hybrid index with semantic/vector configuration
- Parse markdown standards from `standards/` (with required frontmatter)
- Upload chunked coding standards documents with embeddings
- Configure RBAC permissions

**Configure environment variables (optional):**

```bash
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_RESOURCE_GROUP="your-rg"
export AZURE_LOCATION="koreacentral"
export AZURE_AI_SEARCH_SERVICE_NAME="your-search-name"
```

**Run the setup:**

```bash
uv run python scripts/setup_ai_search.py
```

> **Note**: If environment variables are not set, the script will use default values and generate a timestamped service name.

### Index Schema

The standards index includes these key fields:
- `id` (String, Key): Unique document identifier
- `standard_id` (String, Filterable): Logical standard document id
- `standard_type` (String, Filterable): `corporate`, `team`, `repository`, `file_history`, `postmortem`
- `applies_scope` (String, Filterable): `always` or `conditional`
- `title` (String, Searchable): Document title
- `content` (String, Searchable): Standard description and rules
- `tags` (Collection<String>, Filterable): Keywords for filtering
- `applies_to_globs` (Collection<String>, Filterable): File glob targets
- `affected_files` (Collection<String>, Filterable): Explicit file paths
- `content_vector` (Collection<Float>): Embedding vector for hybrid retrieval

### Sample Documents

Sample standards are provided in `standards/` with five categories:

1. Corporate standards (always included)
2. Team standards (always included)
3. Repository standards (always included)
4. File-level action history (included only when reviewed files match)
5. Postmortem action guides (included only when reviewed files match)

Each markdown document must include frontmatter like:

```md
---
standard_id: repo-001
standard_type: repository
title: 리포지토리 표준 - Azure AI Search 조회 규약
applies_scope: always
tags: ["azure-ai-search", "rag"]
language: python
updated_at: 2026-02-24
repo: code-review-agent
team: backend
severity: high
applies_to_globs: ["app/services/**/*.py"]
affected_files: []
related_paths: []
postmortem_id: ""
---
문서 본문...
```

### Authentication

Uses **DefaultAzureCredential** (no API keys needed):
1. Authenticates via `az login`
2. Requires the following Azure RBAC roles:
   - `Search Service Contributor` (for index management)
   - `Search Index Data Contributor` (for querying and indexing)

### Adding Your Own Standards

1. Add markdown files under `standards/` with required frontmatter.
2. Run the setup/indexing script:

```bash
uv run python scripts/setup_ai_search.py
```

The application retrieval logic enforces:
- `corporate`, `team`, `repository` standards are always included.
- `file_history`, `postmortem` are included only when changed files match `affected_files` or `applies_to_globs`.

## Running the Server

### Development

```bash
uv run uvicorn app.main:app --reload --port 8001
```

### Production

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

## API Usage

### Review a Pull Request

```bash
curl -X POST "http://localhost:8001/api/v1/review" \
  -H "Content-Type: application/json" \
  -d '{
    "pr_url": "https://github.com/owner/repo/pull/123",
    "github_pat": "ghp_your_personal_access_token"
  }'
```

### Response Example

```json
{
  "success": true,
  "pr_url": "https://github.com/owner/repo/pull/123",
  "review_id": 12345678,
  "analysis": {
    "issues": [
      {
        "file": "src/utils.py",
        "line": 42,
        "severity": "high",
        "type": "security",
        "description": "SQL injection vulnerability detected",
        "suggestion": "Use parameterized queries instead"
      }
    ],
    "summary": "Found 3 issues including 1 critical security vulnerability",
    "approval_recommendation": "REQUEST_CHANGES",
    "files_reviewed": 5,
    "total_issues": 3,
    "critical_issues": 1
  },
  "message": "Review completed successfully. Found 3 issues.",
  "errors": []
}
```

### Health Check

```bash
curl http://localhost:8001/api/v1/health
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | Required |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Required |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name (Codex recommended) | `gpt-5.2-codex` |
| `AZURE_OPENAI_API_VERSION` | API version | `2025-01-01-preview` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding deployment name | `text-embedding-3-small` |
| `AZURE_AI_SEARCH_ENDPOINT` | Azure AI Search endpoint URL | Optional (for RAG) |
| `AZURE_AI_SEARCH_STANDARDS_INDEX` | Unified standards index | `code-standards-index` |
| `AZURE_AI_SEARCH_TOP_K` | Docs passed to prompt | `5` |
| `AZURE_AI_SEARCH_SEMANTIC_TOP_K` | Docs fetched before filter | `12` |
| `AZURE_AI_SEARCH_MAX_CHARS` | Max chars per doc snippet | `2000` |
| `AZURE_AI_SEARCH_ENABLED` | Enable RAG retrieval | `true` |
| `STANDARDS_DOCS_PATH` | Markdown standards root directory | `standards` |
| `MAX_FILES_PER_REVIEW` | Maximum files to review per PR | `50` |
| `MAX_FILE_SIZE_KB` | Maximum file size to review | `500` |

## GitHub PAT Permissions

Your GitHub Personal Access Token needs the following permissions:
- `repo` - Full control of private repositories (or `public_repo` for public repos only)

## Issue Types Detected

| Type | Description |
|------|-------------|
| 🐛 Bug | Logic errors, potential runtime failures |
| 🔒 Security | Vulnerabilities, unsafe operations |
| ⚡ Performance | Inefficient code, optimization opportunities |
| 🎨 Style | Code formatting, naming conventions |
| 🔧 Maintainability | Code complexity, readability issues |
| 📖 Best Practice | Idiomatic patterns, design improvements |

## Severity Levels

| Level | Description |
|-------|-------------|
| 🚨 Critical | Must fix before merge |
| ⚠️ High | Should fix before merge |
| 📝 Medium | Recommended to fix |
| 💡 Low | Nice to have |
| ℹ️ Info | Informational feedback |

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

Build and run:

```bash
docker build -t code-review-agent .
docker run -p 8001:8001 --env-file .env code-review-agent
```

## License

MIT License
