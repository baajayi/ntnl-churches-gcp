# Multi-stage build for optimized image size
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for Discord bot and other packages
RUN apt-get update && apt-get install -y \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Add Python packages to PATH
ENV PATH=/root/.local/bin:$PATH

# Create non-root user (Cloud Run security best practice)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run uses PORT environment variable (default 8080)
EXPOSE 8080

# Gunicorn with Cloud Run optimized settings
# - Port from $PORT env var (Cloud Run requirement)
# - 2 workers, 4 threads per worker
# - gthread worker class for async Discord bot
# - 120s timeout for long-running RAG queries
# - Access and error logs to stdout (Cloud Logging integration)
CMD exec gunicorn --bind :$PORT \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile - \
    application:application
