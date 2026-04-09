from functools import wraps

from .exceptions import HTTPException


def require_auth(func):
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        if not request.user:
            raise HTTPException(401, "Unauthorized")
        return await func(request, *args, **kwargs)

    return wrapper


def require_role(*roles):
    allowed_roles = set(roles)

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            user = request.user or {}
            user_roles = user.get("roles", [])
            if isinstance(user_roles, str):
                user_roles = [user_roles]

            if not allowed_roles.intersection(user_roles):
                raise HTTPException(403, "Forbidden")

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_permission(*permissions):
    required = set(permissions)

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            user = request.user or {}
            granted = user.get("permissions", [])
            if isinstance(granted, str):
                granted = [granted]

            if not required.issubset(set(granted)):
                raise HTTPException(403, "Forbidden")

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
