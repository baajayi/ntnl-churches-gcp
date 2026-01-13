"""
In-Memory Cache Service
Provides simple in-memory caching with TTL support for conversation history
Thread-safe implementation for concurrent requests
"""

import time
import json
import hashlib
from typing import Any, Optional, Dict, Tuple
from threading import Lock
from collections import OrderedDict


class InMemoryCacheService:
    """Thread-safe in-memory cache with TTL support"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        Initialize in-memory cache

        Args:
            max_size: Maximum number of cache entries (LRU eviction)
            default_ttl: Default time-to-live in seconds (1 hour)
        """
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.lock = Lock()
        self.enabled = True

        print(f"In-memory cache initialized (max_size={max_size}, default_ttl={default_ttl}s)")

    def _make_key(self, tenant_id: str, key: str) -> str:
        """Create namespaced cache key with tenant isolation"""
        return f"tenant:{tenant_id}:{key}"

    def _hash_value(self, value: Any) -> str:
        """Create hash of value for cache key"""
        value_str = json.dumps(value, sort_keys=True)
        return hashlib.md5(value_str.encode()).hexdigest()

    def _is_expired(self, expiry: float) -> bool:
        """Check if cache entry has expired"""
        return time.time() > expiry

    def _evict_expired(self):
        """Remove expired entries (called periodically during operations)"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self.cache.items()
            if current_time > expiry
        ]
        for key in expired_keys:
            del self.cache[key]

    def _enforce_size_limit(self):
        """Enforce max cache size using LRU eviction"""
        while len(self.cache) > self.max_size:
            # Remove oldest entry (FIFO from OrderedDict)
            self.cache.popitem(last=False)

    def get(self, tenant_id: str, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            tenant_id: Tenant identifier
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if not self.enabled:
            return None

        cache_key = self._make_key(tenant_id, key)

        with self.lock:
            # Periodically clean up expired entries
            if len(self.cache) % 100 == 0:
                self._evict_expired()

            if cache_key not in self.cache:
                return None

            value, expiry = self.cache[cache_key]

            # Check if expired
            if self._is_expired(expiry):
                del self.cache[cache_key]
                return None

            # Move to end (mark as recently used)
            self.cache.move_to_end(cache_key)

            return value

    def set(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache

        Args:
            tenant_id: Tenant identifier
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (optional)

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        cache_key = self._make_key(tenant_id, key)
        expiry = time.time() + (ttl or self.default_ttl)

        with self.lock:
            self.cache[cache_key] = (value, expiry)
            self.cache.move_to_end(cache_key)

            # Enforce size limit
            self._enforce_size_limit()

            return True

    def delete(self, tenant_id: str, key: str) -> bool:
        """
        Delete value from cache

        Args:
            tenant_id: Tenant identifier
            key: Cache key

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        cache_key = self._make_key(tenant_id, key)

        with self.lock:
            if cache_key in self.cache:
                del self.cache[cache_key]
            return True

    def clear_tenant_cache(self, tenant_id: str) -> bool:
        """
        Clear all cache entries for a tenant

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        prefix = f"tenant:{tenant_id}:"

        with self.lock:
            keys_to_delete = [
                key for key in self.cache.keys()
                if key.startswith(prefix)
            ]

            for key in keys_to_delete:
                del self.cache[key]

            return True

    def cache_query_result(
        self,
        tenant_id: str,
        query: str,
        result: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache a query result

        Args:
            tenant_id: Tenant identifier
            query: Query string
            result: Query result to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        query_hash = self._hash_value(query)
        key = f"query:{query_hash}"
        return self.set(tenant_id, key, result, ttl)

    def get_cached_query_result(
        self,
        tenant_id: str,
        query: str
    ) -> Optional[Any]:
        """
        Get cached query result

        Args:
            tenant_id: Tenant identifier
            query: Query string

        Returns:
            Cached result or None
        """
        query_hash = self._hash_value(query)
        key = f"query:{query_hash}"
        return self.get(tenant_id, key)

    def cache_embedding(
        self,
        tenant_id: str,
        text: str,
        embedding: list,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache an embedding

        Args:
            tenant_id: Tenant identifier
            text: Original text
            embedding: Embedding vector
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        text_hash = self._hash_value(text)
        key = f"embedding:{text_hash}"
        return self.set(tenant_id, key, embedding, ttl)

    def get_cached_embedding(
        self,
        tenant_id: str,
        text: str
    ) -> Optional[list]:
        """
        Get cached embedding

        Args:
            tenant_id: Tenant identifier
            text: Original text

        Returns:
            Cached embedding or None
        """
        text_hash = self._hash_value(text)
        key = f"embedding:{text_hash}"
        return self.get(tenant_id, key)

    def increment(
        self,
        tenant_id: str,
        key: str,
        amount: int = 1
    ) -> Optional[int]:
        """
        Increment a counter

        Args:
            tenant_id: Tenant identifier
            key: Counter key
            amount: Amount to increment

        Returns:
            New value or None on error
        """
        if not self.enabled:
            return None

        cache_key = self._make_key(tenant_id, key)

        with self.lock:
            if cache_key in self.cache:
                value, expiry = self.cache[cache_key]
                if not self._is_expired(expiry):
                    new_value = int(value) + amount
                    self.cache[cache_key] = (new_value, expiry)
                    return new_value

            # Initialize counter
            expiry = time.time() + self.default_ttl
            self.cache[cache_key] = (amount, expiry)
            return amount

    def expire(self, tenant_id: str, key: str, ttl: int) -> bool:
        """
        Set expiration on existing key

        Args:
            tenant_id: Tenant identifier
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        if not self.enabled:
            return False

        cache_key = self._make_key(tenant_id, key)

        with self.lock:
            if cache_key in self.cache:
                value, _ = self.cache[cache_key]
                new_expiry = time.time() + ttl
                self.cache[cache_key] = (value, new_expiry)
                return True
            return False

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dict with cache stats
        """
        if not self.enabled:
            return {
                'enabled': False,
                'message': 'Cache service disabled'
            }

        with self.lock:
            # Count expired entries
            current_time = time.time()
            expired_count = sum(
                1 for _, (_, expiry) in self.cache.items()
                if current_time > expiry
            )

            return {
                'enabled': True,
                'type': 'in-memory',
                'total_keys': len(self.cache),
                'expired_keys': expired_count,
                'active_keys': len(self.cache) - expired_count,
                'max_size': self.max_size,
                'utilization': f"{(len(self.cache) / self.max_size * 100):.1f}%"
            }


# Singleton instance
_inmemory_cache_service = None


def get_inmemory_cache_service(
    max_size: int = 1000,
    default_ttl: int = 3600
) -> InMemoryCacheService:
    """Get or create InMemoryCacheService singleton"""
    global _inmemory_cache_service
    if _inmemory_cache_service is None:
        _inmemory_cache_service = InMemoryCacheService(
            max_size=max_size,
            default_ttl=default_ttl
        )
    return _inmemory_cache_service
