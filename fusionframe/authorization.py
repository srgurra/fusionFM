from functools import wraps
import inspect

from .auth import has_permission, has_role, normalize_identity
from .exceptions import HTTPException


def _mark_security(func, *, auth=False, roles=None, permissions=None, policy=None):
    existing = getattr(func, "__fusionframe_security__", [])
    security = list(existing)
    if auth and "authenticated" not in security:
        security.append("authenticated")
    setattr(func, "__fusionframe_security__", security)
    if roles:
        current_roles = list(getattr(func, "__fusionframe_roles__", []))
        for role in roles:
            if role not in current_roles:
                current_roles.append(role)
        setattr(func, "__fusionframe_roles__", current_roles)
    if permissions:
        current_permissions = list(getattr(func, "__fusionframe_permissions__", []))
        for permission in permissions:
            if permission not in current_permissions:
                current_permissions.append(permission)
        setattr(func, "__fusionframe_permissions__", current_permissions)
    if policy is not None:
        setattr(func, "__fusionframe_policy__", getattr(policy, "__name__", policy.__class__.__name__))
    return func


def require_auth(func):
    @wraps(func)
    async def wrapper(request, *args, **kwargs):
        if not request.user:
            raise HTTPException(401, "Unauthorized")
        return await func(request, *args, **kwargs)

    return _mark_security(wrapper, auth=True)


def require_role(*roles):
    allowed_roles = set(roles)

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            if not has_role(request.user, *allowed_roles):
                raise HTTPException(403, "Forbidden")

            return await func(request, *args, **kwargs)

        return _mark_security(wrapper, auth=True, roles=allowed_roles)

    return decorator


def require_permission(*permissions):
    required = set(permissions)

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            if not has_permission(request.user, *required):
                raise HTTPException(403, "Forbidden")

            return await func(request, *args, **kwargs)

        return _mark_security(wrapper, auth=True, permissions=required)

    return decorator


def authorize(user, *, roles=None, permissions=None):
    identity = normalize_identity(user)
    if identity is None:
        return False
    if roles and not has_role(identity, *roles):
        return False
    if permissions and not has_permission(identity, *permissions):
        return False
    return True


class AuthorizationPolicy:
    async def authorize(self, request, user):
        raise NotImplementedError


class PolicyRegistry:
    def __init__(self):
        self._policies = {}

    def register(self, name, policy):
        self._policies[name] = policy
        return policy

    def get(self, name):
        return self._policies[name]


async def evaluate_policy(policy, request, user):
    target = policy
    if isinstance(policy, AuthorizationPolicy):
        result = policy.authorize(request, user)
    else:
        result = policy(request, user)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


def build_permission(resource: str, action: str) -> str:
    return f"{resource}:{action}"


def has_resource_permission(user, resource: str, action: str) -> bool:
    return has_permission(
        user,
        build_permission(resource, action),
    ) or has_permission(
        user,
        build_permission(resource, "*"),
    ) or has_permission(
        user,
        build_permission("*", action),
    ) or has_permission(user, "*:*")


def require_resource_permission(action, resource_getter):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            resource = resource_getter(request, *args, **kwargs)
            if inspect.isawaitable(resource):
                resource = await resource
            if not has_resource_permission(request.user, str(resource), action):
                raise HTTPException(403, "Forbidden")
            return await func(request, *args, **kwargs)

        return _mark_security(wrapper, auth=True, permissions=[build_permission("<resource>", action)])

    return decorator


def require_policy(policy):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            if not await evaluate_policy(policy, request, request.user):
                raise HTTPException(403, "Forbidden")
            return await func(request, *args, **kwargs)

        return _mark_security(wrapper, auth=True, policy=policy)

    return decorator
