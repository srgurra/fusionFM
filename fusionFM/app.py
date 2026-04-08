import json
import inspect
from pydantic import ValidationError

from .routing import Router
from .middleware import MiddlewareStack
from .di import inject
from .docs import get_openapi, get_swagger_ui_html
from .http import Request, Response, JSONResponse


class App:
    def __init__(self, title="fusionFM App", version="0.1.0"):
        self.router = Router()
        self.middleware = MiddlewareStack()
        self.routes_meta = []
        self.title = title
        self.version = version

        self._register_builtin_docs_routes()

    def _register_builtin_docs_routes(self):
        async def openapi_handler(request):
            return JSONResponse(
                get_openapi(self.title, self.version, self.routes_meta)
            )

        async def docs_handler(request):
            return Response(
                get_swagger_ui_html("/openapi.json", f"{self.title} Docs"),
                content_type="text/html; charset=utf-8",
            )

        self.router.add_route("GET", "/openapi.json", openapi_handler, None)
        self.router.add_route("GET", "/docs", docs_handler, None)

    def use(self, middleware):
        self.middleware.add(middleware)
        return middleware

    def get(self, path, model=None, dependencies=None):
        return self._add_route("GET", path, model=model, dependencies=dependencies)

    def post(self, path, model=None, dependencies=None):
        return self._add_route("POST", path, model=model, dependencies=dependencies)

    def put(self, path, model=None, dependencies=None):
        return self._add_route("PUT", path, model=model, dependencies=dependencies)

    def delete(self, path, model=None, dependencies=None):
        return self._add_route("DELETE", path, model=model, dependencies=dependencies)

    def _add_route(self, method, path, model=None, dependencies=None):
        def decorator(func):
            wrapped = inject(func, dependencies) if dependencies else func

            self.router.add_route(method, path, wrapped, model)
            self.routes_meta.append(
                {
                    "method": method,
                    "path": path,
                    "model": model.__name__ if model else None,
                    "handler": func.__name__,
                }
            )
            return wrapped

        return decorator

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return

        method = scope["method"]
        path = scope["path"]

        route, path_params = self.router.match(method, path)
        if not route:
            await self._send(send, JSONResponse({"error": "Not Found"}, status_code=404))
            return

        body_bytes = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body_bytes += msg.get("body", b"")
                if not msg.get("more_body", False):
                    break

        try:
            data = json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError:
            await self._send(send, JSONResponse({"error": "Invalid JSON"}, status_code=400))
            return

        if route.get("model"):
            try:
                validated = route["model"](**data)
                data = validated.model_dump()
            except ValidationError as e:
                await self._send(send, JSONResponse({"error": e.errors()}, status_code=400))
                return

        request = Request(scope=scope, body=data, params=path_params or {})

        async def execute(req):
            return await route["handler"](req)

        try:
            result = await self.middleware.run(request, execute)
        except Exception as e:
            await self._send(
                send,
                JSONResponse({"error": "Internal Server Error", "detail": str(e)}, status_code=500),
            )
            return

        response = self._normalize_response(result)
        await self._send(send, response)
        await self._run_background_tasks(request)

    async def _run_background_tasks(self, request):
        for func, args, kwargs in request.background.tasks:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

    def _normalize_response(self, result):
        if isinstance(result, Response):
            return result

        if isinstance(result, tuple) and len(result) == 2:
            content, status_code = result
            if isinstance(content, Response):
                content.status_code = status_code
                return content
            return JSONResponse(content, status_code=status_code)

        if isinstance(result, str):
            return Response(result, content_type="text/plain; charset=utf-8")

        return JSONResponse(result)

    async def _send(self, send, response: Response):
        body = response.render()
        headers = [(b"content-type", response.content_type.encode("utf-8"))]

        for k, v in response.headers.items():
            headers.append((k.lower().encode("utf-8"), str(v).encode("utf-8")))

        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})