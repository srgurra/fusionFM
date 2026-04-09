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
    print(f"[fusionFM] {request.method} {request.path}")
    return await call_next()


async def security_headers_middleware(request, call_next):
    response = await call_next()
    headers = request.state.setdefault("_response_headers", {})
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "same-origin")
    return response
