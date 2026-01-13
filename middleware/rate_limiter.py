"""
Rate Limiter Middleware
Token bucket algorithm for per-tenant rate limiting
"""

import time
from typing import Dict, Any
from services.cache_service import CacheService


class RateLimiter:
    """Rate limiter using token bucket algorithm with Redis backend"""

    def __init__(self, cache_service: CacheService):
        """
        Initialize rate limiter

        Args:
            cache_service: CacheService instance for storing rate limit data
        """
        self.cache = cache_service
        self.window_size = 60  # 1 minute window

    def check_rate_limit(
        self,
        tenant_id: str,
        limit: int
    ) -> Dict[str, Any]:
        """
        Check if request is within rate limit

        Args:
            tenant_id: Tenant identifier
            limit: Maximum requests per minute

        Returns:
            Dict with 'allowed' boolean and optional 'retry_after'
        """
        if not self.cache.enabled:
            # No rate limiting if cache is disabled
            return {'allowed': True}

        current_time = int(time.time())
        window_start = current_time - self.window_size

        # Key for this tenant's rate limit data
        key = f"ratelimit:{current_time // self.window_size}"

        try:
            # Get current count
            current_count = self.cache.get(tenant_id, key)

            if current_count is None:
                # First request in this window
                self.cache.set(tenant_id, key, 1, ttl=self.window_size)
                return {'allowed': True, 'remaining': limit - 1}

            if current_count >= limit:
                # Rate limit exceeded
                retry_after = self.window_size - (current_time % self.window_size)
                return {
                    'allowed': False,
                    'retry_after': retry_after,
                    'limit': limit,
                    'remaining': 0
                }

            # Increment counter
            new_count = current_count + 1
            self.cache.set(tenant_id, key, new_count, ttl=self.window_size)

            return {
                'allowed': True,
                'remaining': limit - new_count,
                'limit': limit
            }

        except Exception as e:
            # On error, allow request (fail open)
            print(f"Rate limiter error: {e}")
            return {'allowed': True}

    def get_rate_limit_status(
        self,
        tenant_id: str,
        limit: int
    ) -> Dict[str, Any]:
        """
        Get current rate limit status without incrementing

        Args:
            tenant_id: Tenant identifier
            limit: Maximum requests per minute

        Returns:
            Dict with rate limit status
        """
        if not self.cache.enabled:
            return {
                'enabled': False,
                'message': 'Rate limiting disabled'
            }

        current_time = int(time.time())
        key = f"ratelimit:{current_time // self.window_size}"

        current_count = self.cache.get(tenant_id, key) or 0

        return {
            'enabled': True,
            'limit': limit,
            'used': current_count,
            'remaining': max(0, limit - current_count),
            'window_size': self.window_size,
            'reset_at': ((current_time // self.window_size) + 1) * self.window_size
        }

    def reset_rate_limit(self, tenant_id: str) -> bool:
        """
        Reset rate limit for a tenant

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if successful
        """
        current_time = int(time.time())
        key = f"ratelimit:{current_time // self.window_size}"

        return self.cache.delete(tenant_id, key)
