import os
import time
import redis
from functools import wraps

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
RATE_LIMIT_PREFIX = os.getenv("RATE_LIMIT_PREFIX", "fusionFM:ratelimit:")

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True,
)


def _client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    client = request.scope.get("client")
    if client and len(client) >= 1:
        return client[0]

    return "unknown"


def rate_limit(limit: int, per: int = 60, key_prefix: str = ""):
    """
    limit: max requests
    per: time window in seconds
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            ip = _client_ip(request)
            path = request.path
            bucket = int(time.time() // per)

            key_base = key_prefix or func.__name__
            key = f"{RATE_LIMIT_PREFIX}{key_base}:{path}:{ip}:{bucket}"

            try:
                current = r.incr(key)
                if current == 1:
                    r.expire(key, per)
            except Exception:
                # Fail open if Redis is unavailable
                return await func(request, *args, **kwargs)

            if current > limit:
                return {
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": per,
                }, 429

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator