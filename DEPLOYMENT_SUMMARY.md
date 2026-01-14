# GCP Cloud Run Deployment Summary

## Deployment Status: ✅ SUCCESSFUL

Your multitenant RAG application has been successfully deployed to GCP Cloud Run!

### Service Information

- **Service Name**: ntnl-churches
- **Region**: us-central1
- **Project ID**: zeta-bonfire-476018-u6
- **Service URL**: https://ntnl-churches-414148512983.us-central1.run.app
- **Current Revision**: ntnl-churches-00003-vb8
- **Image**: us-central1-docker.pkg.dev/zeta-bonfire-476018-u6/ntnl-churches/ntnl-churches:v2

### Configuration

**Compute Resources**:
- Memory: 512Mi
- CPU: 1 vCPU
- Concurrency: 80 requests/instance
- Min instances: 0 (scales to zero when idle)
- Max instances: 10
- Timeout: 120s

**Environment Variables**:
- `FLASK_ENV=production`
- `CACHE_TYPE=memory`
- `GCS_LOGS_BUCKET=ntnl-churches-logs`
- `PINECONE_INDEX_NAME=multitenant-rag`
- `PINECONE_ENVIRONMENT=us-east-1`
- `GOOGLE_CLOUD_PROJECT=zeta-bonfire-476018-u6`
- `OPENAI_EMBEDDING_MODEL=text-embedding-3-large` (3072 dimensions)
- `OPENAI_CHAT_MODEL=gpt-4o-mini`

**Secrets** (from Secret Manager):
- `OPENAI_API_KEY` ✅
- `PINECONE_API_KEY` ✅
- `DISCORD_TOKEN` ✅
- `CHATBOT_API_KEY` ✅

**Service Account**: `ntnl-churches-runtime@zeta-bonfire-476018-u6.iam.gserviceaccount.com`
- Permissions: Storage Object Admin, Secret Manager Accessor

**Access**: Public (--allow-unauthenticated)

## Testing the Deployment

### Health Check
```bash
curl https://ntnl-churches-414148512983.us-central1.run.app/health
```
**Expected**: `{"service":"multitenant-rag-api","status":"healthy","version":"1.0.0"}`

### Query API (NTNL Tenant)
```bash
curl -X POST https://ntnl-churches-414148512983.us-central1.run.app/query \
  -H "X-Tenant-ID: ntnl" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is grace?"}'
```

### Query API (Other Tenants)
Available tenants: `ntnl`, `cts`, `ecic`, `demo`, `bible`, `advent`, `bethel`, `covenant`

```bash
# Example: CTS tenant
curl -X POST https://ntnl-churches-414148512983.us-central1.run.app/query \
  -H "X-Tenant-ID: cts" \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about your church"}'
```

### Get Tenant Stats
```bash
curl https://ntnl-churches-414148512983.us-central1.run.app/stats \
  -H "X-Tenant-ID: ntnl"
```

### Search (Vector Similarity Only)
```bash
curl -X POST https://ntnl-churches-414148512983.us-central1.run.app/search \
  -H "X-Tenant-ID: ntnl" \
  -H "Content-Type: application/json" \
  -d '{"query": "Lutheran theology", "top_k": 5}'
```

## GCP Resources Created

### Cloud Run
- Service: `ntnl-churches` (deployed and serving traffic)

### Cloud Storage
- Bucket: `ntnl-churches-logs`
- Location: us-central1
- Lifecycle: Delete after 90 days, archive after 30 days

### Artifact Registry
- Repository: `ntnl-churches`
- Format: Docker
- Location: us-central1
- Images: v1, v2 (latest)

### Secret Manager
- `OPENAI_API_KEY` (populated)
- `PINECONE_API_KEY` (populated)
- `DISCORD_TOKEN` (populated with placeholder)
- `CHATBOT_API_KEY` (populated with placeholder)

### Service Accounts
1. **Runtime**: `ntnl-churches-runtime@zeta-bonfire-476018-u6.iam.gserviceaccount.com`
   - Used by Cloud Run service
   - Permissions: Storage Object Admin, Secret Accessor

2. **Deployer**: `github-actions-deployer@zeta-bonfire-476018-u6.iam.gserviceaccount.com`
   - Used by GitHub Actions (when Workload Identity is configured)
   - Permissions: Cloud Run Admin, Artifact Registry Writer

## Viewing Logs

### Cloud Run Logs
```bash
# All logs
gcloud logging read "resource.type=cloud_run_revision" \
  --project=zeta-bonfire-476018-u6 \
  --limit=50

# Filter by service
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ntnl-churches" \
  --project=zeta-bonfire-476018-u6 \
  --limit=50

# View in console
https://console.cloud.google.com/logs/query?project=zeta-bonfire-476018-u6
```

### Application Logs (GCS Bucket)
```bash
# List tenant logs
gsutil ls gs://ntnl-churches-logs/logs/

# View NTNL tenant logs
gsutil cat gs://ntnl-churches-logs/logs/ntnl.log | tail -20

# Download logs
gsutil cp gs://ntnl-churches-logs/logs/ntnl.log ./
```

## Cost Estimation

**Monthly GCP Costs** (low traffic, scales to zero):
- Cloud Run: $5-8/month (serverless, pay per use)
- Cloud Storage (10GB logs): $0.50/month
- Artifact Registry: $0.10/month
- Secret Manager: $0.10/month
- Cloud Logging: $2.50/month
- Networking: $1-3/month

**Estimated Total**: $9-14/month

**Cost Advantages**:
- Scales to zero when idle (no 24/7 compute costs like AWS)
- No separate load balancer ($16/month savings vs AWS)
- Pay only for actual request processing time

## Troubleshooting

### Container Not Starting
Check logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ntnl-churches" --limit=20`

### Embedding Dimension Mismatch
Ensure `OPENAI_EMBEDDING_MODEL=text-embedding-3-large` is set (3072 dimensions)

### Secret Access Issues
Verify service account has `secretmanager.secretAccessor` role:
```bash
gcloud projects get-iam-policy zeta-bonfire-476018-u6 \
  --flatten="bindings[].members" \
  --filter="bindings.members:ntnl-churches-runtime@zeta-bonfire-476018-u6.iam.gserviceaccount.com"
```

### Cold Start Latency
First request after idle may take 5-10 seconds. Set `--min-instances=1` to keep one instance warm:
```bash
gcloud run services update ntnl-churches \
  --region=us-central1 \
  --min-instances=1 \
  --project=zeta-bonfire-476018-u6
```

## Next Steps

### 1. Update Discord Bot Configuration (Optional)
If you want the Discord bot to work, update the secrets:
```bash
echo -n "YOUR_REAL_DISCORD_TOKEN" | gcloud secrets versions add DISCORD_TOKEN --data-file=- --project=zeta-bonfire-476018-u6
echo -n "YOUR_REAL_CHATBOT_KEY" | gcloud secrets versions add CHATBOT_API_KEY --data-file=- --project=zeta-bonfire-476018-u6
```

Then redeploy: `gcloud run services update ntnl-churches --region=us-central1`

### 2. Setup GitHub Actions (Optional)
**Status**: ⚠️ Workload Identity Pool creation failed (permissions issue)

To enable automated deployments via GitHub Actions, you need to:
1. Create Workload Identity Pool (requires `iam.workloadIdentityPools.create` permission)
2. Add GitHub repository secrets:
   - `GCP_WORKLOAD_IDENTITY_PROVIDER`
   - `GCP_SERVICE_ACCOUNT`

Once setup, pushing to `main` branch will automatically deploy to Cloud Run.

### 3. Setup Custom Domain (Optional)
Map a custom domain to your Cloud Run service:
```bash
gcloud beta run domain-mappings create --service=ntnl-churches --domain=your-domain.com --region=us-central1
```

### 4. Monitoring and Alerts
Setup alerts in Cloud Monitoring:
- Error rate > 1%
- Latency p95 > 2000ms
- Daily cost exceeds $1

### 5. Performance Optimization
Based on actual usage, consider:
- Adjusting min-instances (0 or 1)
- Adjusting memory (512Mi or 1Gi)
- Tuning concurrency per instance
- Enabling Cloud CDN for static assets

## Comparing AWS vs GCP

### AWS Elastic Beanstalk (~$26/month)
- EC2 t3.micro (always running): $7.50/month
- Application Load Balancer: $16/month
- S3 storage: $1/month
- **Status**: Still running, unchanged

### GCP Cloud Run (~$9-14/month)
- Serverless compute (scales to zero): $5-8/month
- Cloud Storage: $0.50/month
- No load balancer cost
- **Status**: Now deployed and running

**Both environments share**:
- Same Pinecone vector database (multitenant-rag index)
- Same OpenAI API keys
- Same tenant configurations
- Independent logging buckets

## Architecture Notes

### Discord Bot Integration
- Runs as daemon thread within Flask application
- Starts automatically with Cloud Run service
- Gracefully handles missing Discord credentials

### Logging Service
- Uses Cloud Storage instead of AWS S3
- Same NDJSON format
- Same tenant-isolated structure: `logs/{tenant_id}.log`
- Batched uploads every 60 seconds or 100 logs

### Secret Management
- Fetches from Secret Manager at startup
- Falls back to environment variables for local dev
- Uses Application Default Credentials (service account)

### Multi-Tenant Routing
- Header-based: `X-Tenant-ID: ntnl`
- Subdomain-based: `ntnl.yourdomain.com` (if custom domain configured)
- Path-based: `/ntnl/query` (if configured)

## Support

For issues with this deployment:
1. Check Cloud Run logs (see "Viewing Logs" section)
2. Verify environment variables are set correctly
3. Check Secret Manager secrets are populated
4. Ensure service account has proper IAM roles

## Deployment History

- **2026-01-14 00:10 UTC**: Initial deployment (v1) - Failed (permission error)
- **2026-01-14 00:11 UTC**: Second deployment (v2) - Started but failed (embedding mismatch)
- **2026-01-14 00:12 UTC**: Configuration update (v3) - ✅ SUCCESS

## Git Repository

Local path: `/home/bam/ntnl-churches-gcp`

Recent commits:
```
c51ff94 - Fix Docker permissions and environment configuration for Cloud Run
16f8e28 - Update project ID to zeta-bonfire-476018-u6
1a2f4f5 - Initial GCP version from AWS codebase
```

To push to remote (if not already done):
```bash
cd /home/bam/ntnl-churches-gcp
git remote add origin <your-github-repo-url>
git push -u origin main
```
