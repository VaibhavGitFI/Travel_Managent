"""
TravelSync Pro — Cross-Instance State Store

Uses Redis when available, falls back to in-process dicts for local dev.
Provides a dict-like StateNamespace interface with automatic TTL expiry.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                _redis_client = redis.Redis.from_url(
                    redis_url, decode_responses=True, socket_timeout=2
                )
                _redis_client.ping()
                logger.info("[StateStore] Redis connected")
            except Exception as exc:
                logger.warning("[StateStore] Redis unavailable (%s), using in-process fallback", exc)
                _redis_client = False
        else:
            _redis_client = False  # Sentinel: attempted, not available
            logger.debug("[StateStore] No REDIS_URL, using in-process fallback")
    return _redis_client if _redis_client else None


class StateNamespace:
    """Dict-like interface backed by Redis or in-process dict.

    Behaves like a standard dict for reads/writes but supports Redis
    for cross-instance state in Cloud Run / multi-worker deployments.
    """

    def __init__(self, prefix: str, ttl_seconds: int = 3600):
        self._prefix = prefix
        self._ttl = ttl_seconds
        self._local: dict = {}  # fallback for local dev

    def _key(self, k: str) -> str:
        return f"ts:{self._prefix}:{k}"

    def get(self, key: str, default=None):
        r = _get_redis()
        if r:
            try:
                val = r.get(self._key(key))
                return json.loads(val) if val else default
            except Exception:
                return default
        return self._local.get(key, default)

    def set(self, key: str, value):
        r = _get_redis()
        if r:
            try:
                r.setex(self._key(key), self._ttl, json.dumps(value, default=str))
            except Exception as exc:
                logger.warning("[StateStore] Redis set failed: %s", exc)
                self._local[key] = value
        else:
            self._local[key] = value

    def delete(self, key: str):
        r = _get_redis()
        if r:
            try:
                r.delete(self._key(key))
            except Exception:
                pass
        self._local.pop(key, None)

    def pop(self, key: str, default=None):
        val = self.get(key, default)
        self.delete(key)
        return val

    # Dict-like interface so existing code using dict syntax still works
    def __contains__(self, key: str) -> bool:
        r = _get_redis()
        if r:
            try:
                return bool(r.exists(self._key(key)))
            except Exception:
                pass
        return key in self._local

    def __getitem__(self, key: str):
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value):
        self.set(key, value)

    def __delitem__(self, key: str):
        self.delete(key)
