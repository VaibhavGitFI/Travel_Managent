"""
TravelSync Pro — Unified Cache Service
Optional Redis with automatic TTLCache fallback.
Set REDIS_URL in .env to enable Redis (e.g. redis://localhost:6379/0).
Without Redis, all caching uses in-memory TTLCache — zero config needed.
"""
import os
import json
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False


def _init_redis():
    """Try to connect to Redis. Silent fallback if unavailable."""
    global _redis_client, _redis_available
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return

    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        _redis_available = True
        logger.info("[Cache] Redis connected: %s", redis_url.split("@")[-1] if "@" in redis_url else redis_url)
    except Exception as e:
        _redis_client = None
        _redis_available = False
        logger.info("[Cache] Redis unavailable (%s), using in-memory cache", e)


# Initialize on import
_init_redis()


class CacheStore:
    """
    Unified cache with Redis primary and TTLCache fallback.
    Usage:
        cache = CacheStore(namespace="weather", ttl=1800, maxsize=100)
        cache.get("current_mumbai")
        cache.set("current_mumbai", data)
        cache.delete("current_mumbai")
    """

    def __init__(self, namespace: str = "default", ttl: int = 300, maxsize: int = 100):
        self.namespace = namespace
        self.ttl = ttl
        self._local = TTLCache(maxsize=maxsize, ttl=ttl)

    def _redis_key(self, key: str) -> str:
        return f"ts:{self.namespace}:{key}"

    def get(self, key: str):
        """Get a value. Tries Redis first, then local cache."""
        if _redis_available and _redis_client:
            try:
                raw = _redis_client.get(self._redis_key(key))
                if raw is not None:
                    return json.loads(raw)
            except Exception:
                pass

        return self._local.get(key)

    def set(self, key: str, value, ttl: int = None):
        """Set a value in both Redis (if available) and local cache."""
        effective_ttl = ttl or self.ttl

        # Always set local
        self._local[key] = value

        if _redis_available and _redis_client:
            try:
                _redis_client.setex(
                    self._redis_key(key),
                    effective_ttl,
                    json.dumps(value, default=str),
                )
            except Exception:
                pass

    def delete(self, key: str):
        """Remove a key from both stores."""
        self._local.pop(key, None)
        if _redis_available and _redis_client:
            try:
                _redis_client.delete(self._redis_key(key))
            except Exception:
                pass

    def clear(self):
        """Clear all keys in this namespace."""
        self._local.clear()
        if _redis_available and _redis_client:
            try:
                pattern = self._redis_key("*")
                keys = _redis_client.keys(pattern)
                if keys:
                    _redis_client.delete(*keys)
            except Exception:
                pass

    @property
    def is_redis(self) -> bool:
        return _redis_available


# Pre-configured store instances for common use cases
weather_cache = CacheStore(namespace="weather", ttl=1800, maxsize=100)    # 30 min
currency_cache = CacheStore(namespace="currency", ttl=3600, maxsize=10)   # 1 hr
amadeus_cache = CacheStore(namespace="amadeus", ttl=300, maxsize=50)      # 5 min
session_cache = CacheStore(namespace="session", ttl=86400, maxsize=500)   # 24 hr


def get_cache_status() -> dict:
    """Return cache backend info for health check."""
    return {
        "backend": "redis" if _redis_available else "memory",
        "redis_url": bool(os.getenv("REDIS_URL")),
        "redis_connected": _redis_available,
    }
