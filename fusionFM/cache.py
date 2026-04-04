import os
import json
import redis
from functools import wraps

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
CACHE_PREFIX = os.getenv("CACHE_PREFIX", "fusionFM:")

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True,
)


def _key(key: str) -> str:
    return f"{CACHE_PREFIX}{key}"


def cache_get(key: str):
    try:
        value = r.get(_key(key))
        return json.loads(value) if value else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int = 60):
    try:
        r.set(_key(key), json.dumps(value), ex=ttl)
    except Exception:
        pass


def cache_delete(key: str):
    try:
        r.delete(_key(key))
    except Exception:
        pass


def build_cache_key(request, prefix: str = "") -> str:
    key_data = {
        "path": request.path,
        "params": request.params,
        "query": request.query,
        "body": request.body,
    }
    serialized = json.dumps(key_data, sort_keys=True, default=str)
    return f"{prefix}:{serialized}" if prefix else serialized


def cache(ttl: int = 60, key_prefix: str = ""):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            key = build_cache_key(request, prefix=key_prefix or func.__name__)
            cached = cache_get(key)
            if cached is not None:
                return cached

            result = await func(request, *args, **kwargs)
            cache_set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator