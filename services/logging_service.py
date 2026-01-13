"""
Simple Cloud Storage-Based Logging Service
Logs query, response, and time to a single file per tenant on Cloud Storage
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List
import threading
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError, NotFound
import pytz


class LoggingService:
    """Service for logging query events to Cloud Storage with tenant isolation"""

    def __init__(self):
        """Initialize Cloud Storage-based logging service"""
        self.bucket_name = os.getenv('GCS_LOGS_BUCKET', 'ntnl-churches-logs')
        self.enabled = False
        self.storage_client = None
        self.bucket = None
        self.lock = threading.Lock()  # Thread safety for Cloud Storage operations

        # Initialize Cloud Storage client
        try:
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(self.bucket_name)
            print(f"Logging enabled with Cloud Storage. Bucket: {self.bucket_name}")
            self.enabled = True
            self._ensure_bucket_exists()
        except Exception as e:
            print(f"WARNING: Failed to initialize Cloud Storage client: {e}")
            print("Logging to Cloud Storage will be disabled.")
            return

    def _ensure_bucket_exists(self):
        """Ensure Cloud Storage bucket exists, create if not"""
        try:
            if not self.bucket.exists():
                # Create bucket in us-central1 region
                self.storage_client.create_bucket(self.bucket, location='us-central1')
                print(f"Created Cloud Storage bucket: {self.bucket_name}")
        except GoogleCloudError as e:
            print(f"Error checking/creating bucket: {e}")

    def _get_blob_name(self, tenant_id: str) -> str:
        """Get the Cloud Storage blob name for a tenant's log file"""
        return f"logs/{tenant_id}.log"

    def _read_log_from_gcs(self, tenant_id: str) -> List[str]:
        """Read existing log lines from Cloud Storage"""
        if not self.enabled:
            return []

        blob_name = self._get_blob_name(tenant_id)

        try:
            blob = self.bucket.blob(blob_name)
            content = blob.download_as_text()
            return content.strip().split('\n') if content.strip() else []
        except NotFound:
            # Blob doesn't exist yet, return empty list
            return []
        except GoogleCloudError as e:
            print(f"Error reading log from Cloud Storage for tenant {tenant_id}: {e}")
            return []

    def log_query(
        self,
        tenant_id: str,
        query: str,
        response: str,
        time_ms: int,
        metadata: Dict[str, Any] = None
    ):
        """
        Log a query event to the tenant's Cloud Storage log file

        Args:
            tenant_id: Tenant identifier
            query: The user's query
            response: The assistant's response
            time_ms: Time taken in milliseconds
            metadata: Optional additional metadata
        """
        if not self.enabled:
            return

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'tenant_id': tenant_id,
            'query': query,
            'response': response,
            'time_ms': time_ms
        }

        # Add optional metadata if provided
        if metadata:
            log_entry['metadata'] = metadata

        # Append to tenant's log file on Cloud Storage
        blob_name = self._get_blob_name(tenant_id)

        with self.lock:
            try:
                # Read existing logs
                existing_lines = self._read_log_from_gcs(tenant_id)

                # Append new entry
                existing_lines.append(json.dumps(log_entry))

                # Write back to Cloud Storage
                log_content = '\n'.join(existing_lines) + '\n'
                blob = self.bucket.blob(blob_name)
                blob.upload_from_string(
                    log_content,
                    content_type='application/x-ndjson'
                )
            except Exception as e:
                print(f"Error writing to Cloud Storage log for tenant {tenant_id}: {e}")

    def log_event(
        self,
        tenant_id: str,
        event_type: str,
        data: Dict[str, Any],
        severity: str = 'info'
    ):
        """
        Legacy method for compatibility - only logs query events
        Other event types are ignored in the simplified version

        Args:
            tenant_id: Tenant identifier
            event_type: Type of event (only 'query' is logged)
            data: Event data dictionary
            severity: Log severity (ignored in simplified version)
        """
        # Only log query events in the simplified version
        if event_type == 'query':
            query = data.get('query', '')
            response = data.get('response', '')
            time_ms = data.get('latency_ms', 0)

            # Extract additional metadata if available
            metadata = {
                'tokens_used': data.get('tokens_used'),
                'sources_count': data.get('sources_count')
            }

            self.log_query(tenant_id, query, response, time_ms, metadata)

    def get_logs(
        self,
        tenant_id: str,
        start_date: datetime = None,
        end_date: datetime = None,
        event_type: str = None,
        severity: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Retrieve recent logs for a tenant from Cloud Storage with optional filtering

        Args:
            tenant_id: Tenant identifier
            start_date: Optional start datetime for filtering
            end_date: Optional end datetime for filtering
            event_type: Optional event type filter (currently unused in schema)
            severity: Optional severity filter (currently unused in schema)
            limit: Maximum number of log entries to return

        Returns:
            Dict with logs and metadata
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'Logging service is disabled. Cloud Storage credentials not available.',
                'logs': []
            }

        try:
            # Read logs from Cloud Storage
            lines = self._read_log_from_gcs(tenant_id)

            if not lines:
                return {
                    'success': True,
                    'logs': [],
                    'count': 0,
                    'message': 'No logs found for this tenant'
                }

            # Parse log entries and apply filters
            logs = []
            for line in lines:
                if not line.strip():
                    continue

                try:
                    log_entry = json.loads(line)

                    # Apply date filters
                    if start_date or end_date:
                        try:
                            log_timestamp = datetime.fromisoformat(log_entry['timestamp'])
                            # Make timezone-aware if needed for comparison
                            if log_timestamp.tzinfo is None and (start_date or end_date):
                                # If log timestamp is naive and we're comparing to aware datetimes
                                if (start_date and start_date.tzinfo is not None) or (end_date and end_date.tzinfo is not None):
                                    # Assume naive timestamps are UTC
                                    log_timestamp = pytz.UTC.localize(log_timestamp)

                            if start_date and log_timestamp < start_date:
                                continue
                            if end_date and log_timestamp > end_date:
                                continue
                        except (KeyError, ValueError):
                            # Skip entries with invalid timestamps
                            continue

                    # Apply event_type filter (if field exists in future)
                    if event_type and log_entry.get('event_type') != event_type:
                        continue

                    # Apply severity filter (if field exists in future)
                    if severity and log_entry.get('severity') != severity:
                        continue

                    logs.append(log_entry)

                    # Stop if we hit the limit
                    if len(logs) >= limit:
                        break

                except json.JSONDecodeError:
                    continue

            # Reverse to show most recent first
            logs.reverse()

            return {
                'success': True,
                'logs': logs,
                'count': len(logs),
                'tenant_id': tenant_id
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'logs': []
            }

    def get_log_stats(self, tenant_id: str, days: int = 7) -> Dict[str, Any]:
        """
        Get log statistics for a tenant from Cloud Storage

        Args:
            tenant_id: Tenant identifier
            days: Number of days to analyze (ignored in simplified version)

        Returns:
            Dict with statistics
        """
        if not self.enabled:
            return {
                'success': False,
                'error': 'Logging service is disabled. Cloud Storage credentials not available.'
            }

        try:
            # Read logs from Cloud Storage
            lines = self._read_log_from_gcs(tenant_id)

            if not lines:
                return {
                    'success': True,
                    'tenant_id': tenant_id,
                    'total_logs': 0,
                    'message': 'No logs found for this tenant'
                }

            # Count non-empty lines
            line_count = sum(1 for line in lines if line.strip())

            return {
                'success': True,
                'tenant_id': tenant_id,
                'total_logs': line_count
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def flush(self):
        """Compatibility method - no-op for Cloud Storage logging"""
        pass

    def shutdown(self):
        """Compatibility method - no-op for Cloud Storage logging"""
        pass


# Singleton instance
_logging_service = None


def get_logging_service() -> LoggingService:
    """Get or create LoggingService singleton"""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService()
    return _logging_service
