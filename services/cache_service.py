"""
Cache Service Factory
Handles caching for query results and embeddings with tenant isolation
Supports both Redis and in-memory caching modes
"""

import os
import json
import hashlib
from typing import Any, Optional
import redis
from redis.exceptions import RedisError


class RedisCacheService:
    """Service for caching with Redis"""

    def __init__(self):
        """Initialize Redis cache"""
        self.enabled = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'

        if not self.enabled:
            print("Cache service disabled")
            self.redis_client = None
            return

        # Redis configuration
        redis_url = os.getenv('REDIS_URL')

        if redis_url:
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        else:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0')),
                password=os.getenv('REDIS_PASSWORD'),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )

        # Default TTL (time to live) in seconds
        self.default_ttl = int(os.getenv('CACHE_TTL', '3600'))  # 1 hour

        # Test connection
        try:
            self.redis_client.ping()
            print("Redis cache connected successfully")
        except RedisError as e:
            print(f"Redis connection failed: {e}")
            print("Running without cache")
            self.enabled = False
            self.redis_client = None

    def _make_key(self, tenant_id: str, key: str) -> str:
        """Create namespaced cache key with tenant isolation"""
        return f"tenant:{tenant_id}:{key}"

    def _hash_value(self, value: Any) -> str:
        """Create hash of value for cache key"""
        value_str = json.dumps(value, sort_keys=True)
        return hashlib.md5(value_str.encode()).hexdigest()

    def get(self, tenant_id: str, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            tenant_id: Tenant identifier
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.enabled or not self.redis_client:
            return None

        try:
            cache_key = self._make_key(tenant_id, key)
            value = self.redis_client.get(cache_key)

            if value is None:
                return None

            # Deserialize JSON
            return json.loads(value)

        except (RedisError, json.JSONDecodeError) as e:
            print(f"Cache get error: {e}")
            return None

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
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (optional)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            cache_key = self._make_key(tenant_id, key)
            value_json = json.dumps(value)

            # Set with TTL
            self.redis_client.setex(
                cache_key,
                ttl or self.default_ttl,
                value_json
            )
            return True

        except (RedisError, TypeError, ValueError) as e:
            print(f"Cache set error: {e}")
            return False

    def delete(self, tenant_id: str, key: str) -> bool:
        """
        Delete value from cache

        Args:
            tenant_id: Tenant identifier
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            cache_key = self._make_key(tenant_id, key)
            self.redis_client.delete(cache_key)
            return True

        except RedisError as e:
            print(f"Cache delete error: {e}")
            return False

    def clear_tenant_cache(self, tenant_id: str) -> bool:
        """
        Clear all cache entries for a tenant

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            pattern = self._make_key(tenant_id, '*')
            keys = self.redis_client.keys(pattern)

            if keys:
                self.redis_client.delete(*keys)

            return True

        except RedisError as e:
            print(f"Cache clear error: {e}")
            return False

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
            True if successful, False otherwise
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
            True if successful, False otherwise
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
        if not self.enabled or not self.redis_client:
            return None

        try:
            cache_key = self._make_key(tenant_id, key)
            return self.redis_client.incrby(cache_key, amount)

        except RedisError as e:
            print(f"Cache increment error: {e}")
            return None

    def expire(self, tenant_id: str, key: str, ttl: int) -> bool:
        """
        Set expiration on existing key

        Args:
            tenant_id: Tenant identifier
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            cache_key = self._make_key(tenant_id, key)
            return self.redis_client.expire(cache_key, ttl)

        except RedisError as e:
            print(f"Cache expire error: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dict with cache stats
        """
        if not self.enabled or not self.redis_client:
            return {
                'enabled': False,
                'message': 'Cache service disabled'
            }

        try:
            info = self.redis_client.info()
            return {
                'enabled': True,
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory_human', 'N/A'),
                'total_keys': self.redis_client.dbsize(),
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
                'hit_rate': self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }

        except RedisError as e:
            return {
                'enabled': True,
                'error': str(e)
            }

    def _calculate_hit_rate(self, hits: int, misses: int) -> str:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return '0%'
        return f"{(hits / total * 100):.2f}%"


# Singleton instance
_cache_service = None


def get_cache_service():
    """
    Get or create CacheService singleton

    Returns appropriate cache implementation based on CACHE_TYPE environment variable:
    - 'redis': Use Redis cache (requires Redis server)
    - 'memory': Use in-memory cache (default, no dependencies)
    """
    global _cache_service

    if _cache_service is None:
        cache_type = os.getenv('CACHE_TYPE', 'memory').lower()

        if cache_type == 'redis':
            print("Initializing Redis cache service")
            _cache_service = RedisCacheService()
        else:
            print("Initializing in-memory cache service")
            # Import here to avoid circular dependency
            from services.inmemory_cache import InMemoryCacheService

            max_size = int(os.getenv('CACHE_MAX_SIZE', '1000'))
            default_ttl = int(os.getenv('CACHE_TTL', '3600'))

            _cache_service = InMemoryCacheService(
                max_size=max_size,
                default_ttl=default_ttl
            )

    return _cache_service


# Alias for backwards compatibility
CacheService = get_cache_service
