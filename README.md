# Multitenant RAG Application

A production-ready, multitenant Retrieval Augmented Generation (RAG) application built with Flask, Pinecone, and OpenAI. Features include subdomain-based tenant routing, S3 logging, Redis caching, document ingestion, and an admin dashboard.

## Features

### Core Functionality
- **Multitenant Architecture**: Shared infrastructure with logical isolation via Pinecone namespaces
- **RAG Question Answering**: Context-aware responses using vector search + LLM
- **Document Ingestion**: Support for text, PDF, DOCX, and web URLs
- **Vector Search**: Fast similarity search across documents

### Tenant Isolation & Sharing
- **Subdomain Routing**: `tenant1.yourdomain.com` (primary method)
- **Path Routing**: `yourdomain.com/tenant1` (fallback)
- **Header Routing**: `X-Tenant-ID` header (API-first)
- **Namespace Isolation**: Per-tenant Pinecone namespaces
- **Shared Embeddings**: Optional multi-namespace access for shared knowledge bases

### Production Features
- **S3 Logging**: Tenant-isolated logs with batched uploads
- **Redis Caching**: Query result and embedding caching
- **Rate Limiting**: Per-tenant rate limits with token bucket algorithm
- **Admin Dashboard**: Web UI for tenant management and monitoring
- **Auto-scaling**: AWS Elastic Beanstalk with configurable scaling policies
- **Health Checks**: System and component-level health monitoring

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Load Balancer                         │
│                   (tenant1.domain.com)                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │Tenant Router │  │Rate Limiter  │  │Error Handler │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
         │                   │                    │
         ▼                   ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Pinecone   │    │    Redis     │    │   AWS S3     │
│  (Vectors)   │    │   (Cache)    │    │   (Logs)     │
└──────────────┘    └──────────────┘    └──────────────┘
         │
         ▼
┌──────────────┐
│   OpenAI     │
│  (LLM/Emb)   │
└──────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Pinecone account and API key
- OpenAI API key
- AWS account (for S3 and Elastic Beanstalk)
- Redis server (optional, for caching)

### Local Development Setup

1. **Clone and setup**:
```bash
git clone <your-repo>
cd ntnl-churches
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

3. **Required environment variables**:
```bash
# Pinecone
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=multitenant-rag

# OpenAI
OPENAI_API_KEY=your-openai-api-key

# AWS
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
S3_LOGS_BUCKET=multitenant-rag-logs

# Redis (optional)
REDIS_URL=redis://localhost:6379/0
```

4. **Run the application**:
```bash
python app.py
```

The server will start on `http://localhost:5000`.

## Documentation

- **[INGESTION_GUIDE.md](INGESTION_GUIDE.md)** - Complete guide for populating namespaces with documents
- **[TENANT_CONFIG_GUIDE.md](TENANT_CONFIG_GUIDE.md)** - Configuring system prompts and RAG settings per tenant

### Testing Locally

Since subdomain routing requires DNS setup, test locally using headers:

```bash
# Health check
curl http://localhost:5000/health

# Query with tenant header
curl -X POST http://localhost:5000/query \
  -H "X-Tenant-ID: demo" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is your return policy?"}'

# Ingest a document
curl -X POST http://localhost:5000/ingest/text \
  -H "X-Tenant-ID: demo" \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [{
      "content": "Our return policy allows returns within 30 days.",
      "metadata": {"source": "policy.txt"}
    }]
  }'

# Search for similar content
curl -X POST http://localhost:5000/search \
  -H "X-Tenant-ID: demo" \
  -H "Content-Type: application/json" \
  -d '{"query": "return policy", "top_k": 5}'
```

## Populating Namespaces with Data

Before querying, you need to populate your Pinecone namespaces with documents. There are three methods:

### 1. Bulk Directory Ingestion (Recommended for initial setup)
```bash
# Ingest all documents in a directory to a namespace
python scripts/bulk_ingest.py /path/to/docs --namespace shared

# With category tagging
python scripts/bulk_ingest.py /path/to/policies --namespace tenant1 --category policy
```

### 2. CSV Ingestion (Best for structured data)
```bash
# Ingest FAQ or structured data from CSV
python scripts/ingest_from_csv.py data.csv --namespace shared

# Keep each row as single vector (no chunking)
python scripts/ingest_from_csv.py faq.csv --namespace shared --no-chunk
```

### 3. API Ingestion (For real-time updates)
```bash
# Ingest via API endpoint
curl -X POST http://localhost:5000/ingest/file \
  -H "X-Tenant-ID: shared" \
  -F "file=@document.pdf"
```

**See [INGESTION_GUIDE.md](INGESTION_GUIDE.md) for complete documentation on all ingestion methods.**

## Shared Embeddings Across Tenants

Tenants can access multiple namespaces for shared knowledge bases:

```python
# Configure tenant to access both their own namespace and shared
'tenant1': {
    'accessible_namespaces': ['tenant1', 'shared'],  # Queries both
    ...
}
```

**How it works:**
1. Populate shared namespace: `python scripts/bulk_ingest.py /company-docs --namespace shared`
2. Configure tenants with `accessible_namespaces`
3. Queries automatically search all accessible namespaces and merge results by relevance

## API Endpoints

### RAG Endpoints

#### POST /query
Ask a question with RAG context. If tenant has multiple `accessible_namespaces`, searches all and merges results.

**Request**:
```json
{
  "query": "What is the return policy?",
  "top_k": 5,
  "temperature": 0.7,
  "system_prompt": "You are a helpful assistant...",
  "use_cache": true
}
```

**Response**:
```json
{
  "success": true,
  "answer": "Our return policy allows...",
  "sources": [
    {
      "id": "vec-123",
      "score": 0.92,
      "namespace": "shared",
      "metadata": {...}
    }
  ],
  "metadata": {
    "namespaces_searched": ["tenant1", "shared"],
    "tokens": {...},
    "latency_ms": 1234
  }
}
```

#### POST /search
Vector similarity search without LLM.

#### GET /stats
Get tenant statistics (vector count, cache stats).

### Ingestion Endpoints

#### POST /ingest/text
Ingest raw text documents.

#### POST /ingest/file
Upload and ingest PDF, DOCX, TXT, or MD files.

#### POST /ingest/url
Fetch and ingest content from URL.

#### POST /delete
Delete vectors by ID or filter.

### Logging Endpoints

#### GET /logs
Retrieve logs with filtering.

**Query Parameters**:
- `start_date`: ISO date or YYYY-MM-DD
- `end_date`: ISO date or YYYY-MM-DD
- `event_type`: Filter by event type
- `severity`: Filter by severity (info, warning, error)
- `limit`: Max entries (default 100)

#### GET /logs/stats
Get log statistics (event types, severities, daily counts).

#### GET /logs/recent
Get logs from last 24 hours.

#### GET /logs/errors
Get error and critical logs.

### Admin Dashboard

Access at `http://localhost:5000/admin`:
- `/admin` - Dashboard with tenant overview
- `/admin/tenants` - Tenant management
- `/admin/logs/<tenant_id>` - View tenant logs

## Deployment to AWS Elastic Beanstalk

### Prerequisites

1. Install EB CLI:
```bash
pip install awsebcli
```

2. Configure AWS credentials:
```bash
aws configure
```

### Deploy

1. **Initialize Elastic Beanstalk**:
```bash
eb init -p python-3.11 multitenant-rag-app --region us-east-1
```

2. **Create environment**:
```bash
eb create rag-production \
  --elb-type application \
  --instance-type t3.medium \
  --min-instances 2 \
  --max-instances 10
```

3. **Set environment variables**:
```bash
eb setenv \
  FLASK_ENV=production \
  SECRET_KEY=your-production-secret \
  PINECONE_API_KEY=your-key \
  OPENAI_API_KEY=your-key \
  AWS_ACCESS_KEY_ID=your-key \
  AWS_SECRET_ACCESS_KEY=your-secret \
  S3_LOGS_BUCKET=your-bucket \
  REDIS_URL=your-redis-url
```

4. **Deploy application**:
```bash
eb deploy
```

5. **Check status**:
```bash
eb status
eb health
eb logs
```

### DNS Configuration

1. **Setup wildcard DNS** for subdomains:
```
*.yourdomain.com  CNAME  your-eb-app.elasticbeanstalk.com
```

2. **SSL/TLS Certificate**:
- Request certificate in AWS Certificate Manager
- Add to load balancer listener in EB console

### Post-Deployment

1. **Test endpoints**:
```bash
curl https://demo.yourdomain.com/health
```

2. **Monitor logs** in S3 bucket

3. **Access admin dashboard**:
```
https://yourdomain.com/admin
```

## Configuration

### Tenant Configuration

Edit `TENANT_CONFIG` in `app.py`:

```python
TENANT_CONFIG = {
    'tenant1': {
        'name': 'Tenant One',
        'pinecone_namespace': 'tenant1',
        'accessible_namespaces': ['tenant1', 'shared'],  # Multi-namespace support
        'rate_limit': 100,  # requests per minute
        'enabled': True,
        'system_prompt': 'You are a helpful assistant...',  # Custom prompt
        'rag_settings': {  # Default RAG parameters
            'top_k': 5,
            'temperature': 0.7,
            'max_tokens': 1000
        }
    }
}
```

For production, move this to a database (DynamoDB, PostgreSQL).

**See [TENANT_CONFIG_GUIDE.md](TENANT_CONFIG_GUIDE.md) for detailed configuration options.**

### Cache Configuration

Redis caching is optional but recommended:

```bash
# Disable caching
REDIS_ENABLED=false

# Enable with custom TTL
REDIS_ENABLED=true
CACHE_TTL=7200  # 2 hours
```

### Logging Configuration

S3 logging batches uploads for efficiency:

```bash
LOG_BATCH_SIZE=10        # Logs per batch
LOG_FLUSH_INTERVAL=30    # Seconds between flushes
```

## Infrastructure as Code

### Terraform

See `terraform/` directory for:
- S3 bucket creation
- IAM roles and policies
- (Optional) ElastiCache Redis cluster

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

## Monitoring

### Health Checks

- **Application**: `GET /health`
- **System**: `GET /admin/api/system/health`

### Metrics to Monitor

- Request latency (query, search, ingestion)
- Token usage and costs (OpenAI)
- Cache hit rate (Redis)
- Error rates per tenant
- Vector count per namespace

### CloudWatch

Set up alarms for:
- High error rates
- Elevated latency (>2s)
- High CPU usage (>80%)
- Failed health checks

## Cost Optimization

### Caching Strategy

Enable Redis caching to reduce:
- OpenAI embedding costs (cache frequent texts)
- OpenAI completion costs (cache common queries)
- Pinecone query costs (cache search results)

### Scaling

Adjust auto-scaling triggers based on usage:

```yaml
# .ebextensions/03_environment.config
UpperThreshold: 70  # Scale up at 70% CPU
LowerThreshold: 20  # Scale down at 20% CPU
MinSize: 2          # Minimum instances
MaxSize: 10         # Maximum instances
```

### S3 Lifecycle

Configure S3 lifecycle rules to archive old logs:

```bash
# Move logs older than 30 days to Glacier
# Delete logs older than 365 days
```

## Security Best Practices

1. **API Keys**: Never commit `.env` file
2. **HTTPS Only**: Always use SSL/TLS in production
3. **IAM Roles**: Use least-privilege permissions
4. **Input Validation**: All inputs are validated and sanitized
5. **Rate Limiting**: Prevents abuse and DOS attacks
6. **Tenant Isolation**: Namespaces ensure data separation

## Troubleshooting

### Application won't start

```bash
# Check logs
eb logs

# Common issues:
# - Missing environment variables
# - Invalid API keys
# - S3 bucket doesn't exist
```

### Tenant not found

Verify tenant exists in `TENANT_CONFIG` and subdomain/header matches tenant ID.

### High latency

1. Enable Redis caching
2. Reduce `top_k` in queries
3. Optimize chunk sizes
4. Scale up instances

### Cache not working

```bash
# Test Redis connection
redis-cli ping

# Check logs for Redis errors
tail -f logs/app.log
```

## Development

### Project Structure

```
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── Procfile              # Gunicorn configuration
├── .env.example          # Environment template
│
├── services/             # Business logic layer
│   ├── pinecone_service.py      # Vector DB with multi-namespace support
│   ├── openai_service.py        # Embeddings and LLM
│   ├── logging_service.py       # S3 batched logging
│   └── cache_service.py         # Redis caching
│
├── routes/               # API endpoints
│   ├── rag.py           # Query and search (multi-namespace)
│   ├── ingestion.py     # Document upload
│   ├── logs.py          # Log retrieval
│   └── admin.py         # Admin dashboard
│
├── scripts/              # Standalone ingestion tools
│   ├── bulk_ingest.py   # Directory → Pinecone
│   └── ingest_from_csv.py   # CSV → Pinecone
│
├── middleware/           # Request middleware
│   └── rate_limiter.py
│
├── templates/            # HTML templates
│   └── admin/
│
├── docs/                 # Documentation
│   ├── README.md
│   ├── INGESTION_GUIDE.md      # Data population guide
│   └── TENANT_CONFIG_GUIDE.md  # Configuration guide
│
├── .ebextensions/        # EB configuration
├── .platform/            # Nginx configuration
└── terraform/            # Infrastructure as code
```

### Adding a New Tenant

1. Add to `TENANT_CONFIG`:
```python
'new_tenant': {
    'name': 'New Tenant',
    'pinecone_namespace': 'new_tenant',
    'rate_limit': 100,
    'enabled': True
}
```

2. Create Pinecone namespace:
```python
# Namespace is created automatically on first upsert
```

3. Configure DNS (if using subdomains):
```
new_tenant.yourdomain.com  CNAME  your-app.com
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Your repo URL]
- Email: [Your email]
