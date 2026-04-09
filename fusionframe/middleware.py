from .auth import verify_token
from .sessions import get_session_user


class MiddlewareStack:
    def __init__(self):
        self.middlewares = []

    def add(self, middleware):
        self.middlewares.append(middleware)

    async def run(self, request, handler):
        async def call(index):
            if index < len(self.middlewares):
                current = self.middlewares[index]
                return await current(request, lambda: call(index + 1))
            return await handler(request)

        return await call(0)


async def auth_middleware(request, call_next):
    auth_header = request.get_header("authorization")
    token = None

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]

    request.user = verify_token(token) if token else get_session_user(request)
    return await call_next()


async def logging_middleware(request, call_next):
    print(f"[fusionframe] {request.method} {request.path}")
    return await call_next()


async def security_headers_middleware(request, call_next):
    response = await call_next()
    headers = request.state.setdefault("_response_headers", {})
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "same-origin")
    return response


def cors_middleware(
    *,
    allow_origins=None,
    allow_credentials=False,
    allow_methods=None,
    allow_headers=None,
    expose_headers=None,
    max_age=600,
):
    allow_origins = list(allow_origins or ["*"])
    allow_methods = [method.upper() for method in (allow_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])]
    allow_headers = list(allow_headers or ["Authorization", "Content-Type", "X-CSRF-Token"])
    expose_headers = list(expose_headers or [])

    async def middleware(request, call_next):
        origin = request.get_header("origin")
        allowed_origin = _resolve_allowed_origin(origin, allow_origins)

        if request.method.upper() == "OPTIONS" and request.get_header("access-control-request-method"):
            headers = {}
            if allowed_origin:
                headers["Access-Control-Allow-Origin"] = allowed_origin
                headers["Vary"] = "Origin"
            headers["Access-Control-Allow-Methods"] = ", ".join(allow_methods)
            headers["Access-Control-Allow-Headers"] = ", ".join(allow_headers)
            headers["Access-Control-Max-Age"] = str(max_age)
            if allow_credentials:
                headers["Access-Control-Allow-Credentials"] = "true"
            request.state.setdefault("_response_headers", {}).update(headers)
            return "", 204

        response = await call_next()
        if allowed_origin:
            headers = request.state.setdefault("_response_headers", {})
            headers.setdefault("Access-Control-Allow-Origin", allowed_origin)
            headers.setdefault("Vary", "Origin")
            if allow_credentials:
                headers.setdefault("Access-Control-Allow-Credentials", "true")
            if expose_headers:
                headers.setdefault("Access-Control-Expose-Headers", ", ".join(expose_headers))
        return response

    return middleware


def _resolve_allowed_origin(origin, allow_origins):
    if not origin:
        return None
    if "*" in allow_origins:
        return origin
    if origin in allow_origins:
        return origin
    return None
