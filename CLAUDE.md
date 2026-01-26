# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-ready, multitenant RAG (Retrieval Augmented Generation) application built with Flask, Pinecone vector database, and Google Gemini via Vertex AI. The application serves Lutheran church content through a conversational AI interface with tenant isolation via Pinecone namespaces.

**Key tenant**: NTNL (Northern Texas-Northern Louisiana) - Lutheran Church content delivery

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (development mode)
python app.py

# Run with Gunicorn (production-like)
gunicorn --bind :8000 --workers 2 --threads 4 --timeout 120 application:application
```

### Data Ingestion
```bash
# Ingest local documents
python scripts/bulk_ingest.py /path/to/docs --namespace shared

# Ingest from S3
python scripts/bulk_ingest.py --s3-bucket ntnl-training-data --s3-prefix 'ELCA Values/' --namespace shared

# Ingest from Google Drive
python scripts/bulk_ingest.py --gdrive-folder 1abc123xyz --gdrive-credentials /path/to/creds.json --namespace shared

# Ingest CSV (structured data/FAQ)
python scripts/ingest_from_csv.py data.csv --namespace shared --no-chunk

# With custom options
python scripts/bulk_ingest.py /path/to/docs --namespace shared --batch-size 25 --text-snippet-len 500
```

### AWS Elastic Beanstalk Deployment
```bash
# Initialize EB
eb init -p python-3.11 multitenant-rag-app --region us-east-1

# Create environment
eb create rag-production --elb-type application --instance-type t3.medium

# Deploy updates
eb deploy

# View logs
eb logs

# Set environment variables (Gemini uses IAM auth, no API key needed)
eb setenv PINECONE_API_KEY=xxx GCP_PROJECT_ID=xxx GCP_LOCATION=us-central1
```

### Testing Endpoints
```bash
# Health check
curl http://localhost:5000/health

# Query with tenant header
curl -X POST http://localhost:5000/query \
  -H "X-Tenant-ID: ntnl" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are ELCA values?"}'

# Search (vector similarity without LLM)
curl -X POST http://localhost:5000/search \
  -H "X-Tenant-ID: ntnl" \
  -d '{"query": "Lutheran theology", "top_k": 5}'

# Get tenant stats
curl -H "X-Tenant-ID: ntnl" http://localhost:5000/stats

# View logs
curl -H "X-Tenant-ID: ntnl" http://localhost:5000/logs/recent
```

## Architecture

### Multi-Tenant Isolation Strategy
- **Namespace-based isolation**: Each tenant has one or more Pinecone namespaces
- **Shared embeddings**: Tenants can access multiple namespaces via `accessible_namespaces` config
- **Tenant routing**: Subdomain-based (`tenant.domain.com`), path-based (`/tenant`), or header-based (`X-Tenant-ID`)

### Request Flow
1. **Tenant middleware** (`app.py:before_request`) extracts tenant from subdomain/header/path and loads config into `g.tenant_id` and `g.tenant_config`
2. **Rate limiter** (`middleware/rate_limiter.py`) enforces per-tenant rate limits using token bucket algorithm
3. **Route handlers** (`routes/`) process the request
4. **Service layer** (`services/`) handles business logic:
   - `gemini_service.py`: Embeddings + LLM completion via Vertex AI with conversation history support
   - `pinecone_service.py`: Multi-namespace vector search and upsert
   - `cache_service.py`: In-memory or Redis caching
   - `logging_service.py`: S3-based tenant-isolated logging with batched uploads
5. **Response** includes sources with namespace info and cache status

### Multi-Namespace Query Pattern
When `accessible_namespaces: ['tenant1', 'shared']` is configured:
- Query embedding is created once
- Parallel search across all accessible namespaces
- Results merged and sorted by score
- Response metadata includes `namespaces_searched`

This allows shared knowledge bases (company docs, policies) alongside tenant-specific content.

### Conversation History
The `/query` endpoint supports conversation context:
- Accepts optional `conversation_history` array in request
- Format: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- Enables context-aware follow-up questions
- System prompt explicitly instructs model to reference conversation history for pronouns like "it", "that", "this"

### Widget Architecture
Two Shadow DOM-based JavaScript widgets provide embeddable chat interfaces:
- `cts-floating-widget.js`: Floating chat button with expandable interface
- `cts-iframe-widget.js`: Inline iframe-based widget
- Both use Shadow DOM to avoid CSS conflicts with host page
- Support CORS with `X-Tenant-ID` header for tenant routing
- Mobile-responsive with keyboard detection

## Critical Configuration

### Tenant Config (`app.py`)
All tenant configuration lives in `TENANT_CONFIG` dictionary:
```python
TENANT_CONFIG = {
    'ntnl': {
        'name': 'NTNL - Northern Texas-Northern Louisiana',
        'pinecone_namespace': 'tenant1',
        'accessible_namespaces': ['shared'],  # Multi-namespace access
        'rate_limit': 100,
        'enabled': True,
        'system_prompt': '...',  # Custom prompt for this tenant
        'rag_settings': {
            'top_k': 5,           # Chunks retrieved
            'temperature': 0.7,    # LLM randomness
            'max_tokens': 1000     # Response length
        }
    }
}
```

**Important**: For production, move this to a database (DynamoDB/PostgreSQL). The in-memory dict is for development only.

### Environment Variables
Required variables (see `.env.example`):
- `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`: Vector database
- `GCP_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT`: GCP project for Vertex AI
- `GCP_LOCATION`: Vertex AI region (default: us-central1)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_LOGS_BUCKET`: Logging
- Optional: `REDIS_URL` or `CACHE_TYPE=memory` for caching

**Note**: Gemini uses IAM authentication via Application Default Credentials (ADC). No API key is required. On Cloud Run, the service account automatically has credentials. For local development, use `gcloud auth application-default login`.

### Pinecone Index Specs
- **Dimension**: 3072 (Gemini `gemini-embedding-001` with `output_dimensionality=3072`)
- **Metric**: Cosine similarity
- **Spec**: Serverless (AWS, region from `PINECONE_ENVIRONMENT`)
- Index auto-created on first run if missing

**Note**: The dimension matches the previous OpenAI configuration, so no re-ingestion is needed when migrating.

## Key Design Patterns

### Lazy Service Initialization
Services are initialized via getter functions (`get_pinecone_service()`, `get_gemini_service()`) that cache singletons. This allows services to fail gracefully if credentials are missing and be mocked for testing.

### Namespace as Isolation Boundary
Pinecone namespaces provide logical data isolation without separate indexes. All upsert/query operations require an explicit namespace. This is the **critical security boundary** - always verify tenant namespace before operations.

### Chunking Strategy
Documents are split into overlapping chunks:
- **Default**: 1000 chars with 200 char overlap
- **Rationale**: Balance between context preservation and retrieval precision
- **Metadata**: Each chunk retains source file, category, and position metadata

### Error Handling Pattern
All service methods return `{'success': bool, 'error': str, ...}` dicts instead of raising exceptions. This makes error handling consistent across API boundaries.

### CORS Configuration
Explicit CORS headers are set via `after_request` handler to support Shadow DOM widgets making cross-origin requests. The `X-Tenant-ID` header is exposed and allowed for client-side tenant routing.

## Ingestion Details

### Supported Formats
- **Text**: TXT, MD
- **Documents**: PDF (PyPDF2), DOCX (python-docx)
- **Legacy**: DOC, PPT (via LibreOffice conversion)
- **Cloud**: S3 (boto3), Google Drive (Google API client)
- **Structured**: CSV

### Bulk Ingestion Safeguards
The `bulk_ingest.py` script includes several safety mechanisms:
- Skips empty chunks (prevents "No valid texts provided" errors)
- Embedding micro-batching (avoids per-request token limits)
- Optional page/chunk caps per file (controls huge PDFs)
- Cost estimation (tokens * rate)
- Progress reporting with failure tracking

### CSV Ingestion Pattern
Use `--no-chunk` flag for FAQ/structured data where each row should be a single vector. This prevents splitting Q&A pairs or product descriptions mid-sentence.

## Common Modifications

### Adding a New Tenant
1. Add entry to `TENANT_CONFIG` in `app.py`
2. Ingest tenant-specific docs: `python scripts/bulk_ingest.py /docs --namespace new_tenant`
3. Configure `accessible_namespaces` to include shared namespaces if needed
4. Test: `curl -H "X-Tenant-ID: new_tenant" http://localhost:5000/health`

### Updating System Prompt
Edit `system_prompt` in tenant config. Changes take effect immediately (no restart needed as config is loaded per-request from in-memory dict).

For production database-backed config, implement cache invalidation.

### Changing RAG Parameters
Override in tenant's `rag_settings` or per-request:
```json
{"query": "...", "top_k": 10, "temperature": 0.3}
```
Request params override tenant defaults.

### Adding New Document Sources
To add a new cloud source (Dropbox, OneDrive, etc.):
1. Add API client setup in `bulk_ingest.py`
2. Implement file listing/download logic
3. Use existing `process_file()` function for content extraction
4. Follow the S3/GDrive pattern for temp file cleanup

## Monitoring and Logging

### S3 Logging Structure
Logs are batched and uploaded to S3 with structure:
```
s3://{bucket}/{tenant_id}/logs/{year}/{month}/{day}/{timestamp}.json
```

### Key Events Logged
- `query`: RAG queries with latency and token usage
- `search`: Vector searches
- `ingest`: Document ingestion operations
- `query_cache_hit`: Cache hits
- `error`: Application errors

### Health Check Endpoint
`GET /health` returns:
- Pinecone connectivity and index stats
- Vertex AI (Gemini) availability
- Cache service status
- Per-namespace vector counts

## Testing Considerations

### Widget Testing
Use `cts-widget-test.html` to test widgets locally. Modify the tenant ID and API endpoint as needed.

### Rate Limiting
Rate limiter uses in-memory token bucket. For distributed deployments, consider Redis-backed rate limiting.

### Cache Invalidation
In-memory cache is per-process. For multi-instance deployments, enable Redis caching via `REDIS_URL` environment variable.

## Documentation References

- **INGESTION_GUIDE.md**: Complete guide for data population methods
- **TENANT_CONFIG_GUIDE.md**: System prompt examples and RAG parameter tuning
- **DEPLOYMENT.md**: AWS infrastructure setup and configuration
- **README.md**: Quick start and API reference
