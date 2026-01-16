# Code Review Agent

AI-powered Code Review Agent for GitHub Pull Requests using Azure OpenAI.

## Features

- 🔍 **Automatic PR Analysis**: Analyzes code changes in GitHub Pull Requests
- 🤖 **AI-Powered Reviews**: Uses Azure OpenAI (GPT-4) for intelligent code review
- 💬 **Inline Comments**: Posts review comments directly on specific code lines
- 🎯 **Issue Categorization**: Categorizes issues by type (bug, security, performance, style)
- ⚠️ **Severity Levels**: Rates issues from critical to info
- 💡 **Actionable Suggestions**: Provides code suggestions using GitHub suggestion blocks
- ✅ **Review Decisions**: Recommends APPROVE, REQUEST_CHANGES, or COMMENT

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
├─────────────────────────────────────────────────────────────┤
│  POST /api/v1/review                                        │
│  ├── ReviewService (Orchestration)                          │
│  │   ├── GitHubService (API Integration)                    │
│  │   │   ├── Fetch PR Details                               │
│  │   │   ├── Get Changed Files & Diffs                      │
│  │   │   └── Post Review Comments                           │
│  │   └── AzureOpenAIService (Analysis)                      │
│  │       ├── Analyze Code Changes                           │
│  │       └── Generate Review Feedback                       │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- Azure OpenAI deployment (GPT-4 or GPT-4o recommended)
- GitHub Personal Access Token (PAT) with `repo` scope

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
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
```

## Running the Server

### Development

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### Production

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Usage

### Review a Pull Request

```bash
curl -X POST "http://localhost:8000/api/v1/review" \
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
curl http://localhost:8000/api/v1/health
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | Required |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Required |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name | `gpt-4o` |
| `AZURE_OPENAI_API_VERSION` | API version | `2024-10-21` |
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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t code-review-agent .
docker run -p 8000:8000 --env-file .env code-review-agent
```

## License

MIT License
