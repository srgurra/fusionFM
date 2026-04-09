import json
import inspect
import time
from pydantic import ValidationError

from .routing import Router
from .middleware import MiddlewareStack
from .di import inject
from .docs import get_openapi, get_swagger_ui_html
from .http import Request, Response, JSONResponse, WebSocket, parse_http_body, validate_body_size
from .exceptions import HTTPException, WebSocketException
from .plugins import load_plugin
from .versioning import VersionedAPI


class App:
    def __init__(self, title="fusionFM App", version="0.1.0", max_body_size=None):
        self.router = Router()
        self.middleware = MiddlewareStack()
        self.routes_meta = []
        self.title = title
        self.version = version
        self.state = {}
        self.exception_handlers = {}
        self.plugins = []
        self.startup_handlers = []
        self.shutdown_handlers = []
        self.state["startup_time_ms"] = None
        self.state["started_at"] = None
        self.max_body_size = max_body_size

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

    def websocket(self, path, dependencies=None):
        return self._add_websocket_route(path, dependencies=dependencies)

    def exception_handler(self, exc_class):
        def decorator(func):
            self.exception_handlers[exc_class] = func
            return func

        return decorator

    def plugin(self, plugin):
        plugin_instance = load_plugin(plugin)
        plugin_instance.setup(self)
        self.plugins.append(plugin_instance)
        return plugin_instance

    def on_startup(self, func):
        self.startup_handlers.append(func)
        return func

    def on_shutdown(self, func):
        self.shutdown_handlers.append(func)
        return func

    def api(self, version, prefix=""):
        return VersionedAPI(self, version=version, prefix=prefix)

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

    def _add_websocket_route(self, path, dependencies=None):
        def decorator(func):
            wrapped = inject(func, dependencies) if dependencies else func

            self.router.add_route(None, path, wrapped, protocol="websocket")
            return wrapped

        return decorator

    async def __call__(self, scope, receive, send):
        scope_type = scope["type"]

        if scope_type == "http":
            await self._handle_http(scope, receive, send)
            return

        if scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
            return

        if scope_type == "lifespan":
            await self._handle_lifespan(receive, send)
            return

    async def _handle_http(self, scope, receive, send):
        method = scope["method"]
        path = scope["path"]

        route, path_params = self.router.match(method, path, protocol="http")
        if not route:
            await self._send_error(send, HTTPException(404, "Not Found"))
            return

        body_bytes = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body_bytes += msg.get("body", b"")
                try:
                    validate_body_size(
                        body_bytes,
                        max_body_size=self.max_body_size or 1024 * 1024 * 10,
                    )
                except ValueError as exc:
                    await self._send_error(send, HTTPException(413, str(exc)))
                    return
                if not msg.get("more_body", False):
                    break

        headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }

        try:
            data, form_data, files = parse_http_body(headers, body_bytes)
        except json.JSONDecodeError:
            await self._send_error(send, HTTPException(400, "Invalid JSON"))
            return
        except ValueError as exc:
            await self._send_error(send, HTTPException(400, str(exc)))
            return

        if route.get("model"):
            try:
                validated = route["model"](**data)
                data = validated.model_dump()
            except ValidationError as e:
                await self._send_error(send, e)
                return

        request = Request(
            scope=scope,
            body=data,
            params=path_params or {},
            raw_body=body_bytes,
            form=form_data,
            files=files,
        )

        async def execute(req):
            return await route["handler"](req)

        try:
            result = await self.middleware.run(request, execute)
        except Exception as exc:
            await self._send_error(send, exc)
            return

        response = self._normalize_response(result)
        extra_headers = request.state.get("_response_headers", {})
        for key, value in extra_headers.items():
            response.headers.setdefault(key, value)
        session_cookie = request.state.get("_session_cookie")
        if session_cookie:
            response.headers["Set-Cookie"] = session_cookie
        await self._send(send, response)
        await self._run_background_tasks(request)

    async def _handle_websocket(self, scope, receive, send):
        path = scope["path"]
        route, path_params = self.router.match(None, path, protocol="websocket")

        connect_message = await receive()
        if connect_message["type"] != "websocket.connect":
            await send({"type": "websocket.close", "code": 1002})
            return

        if not route:
            await send({"type": "websocket.close", "code": 1008, "reason": "Not Found"})
            return

        websocket = WebSocket(
            scope=scope,
            receive=receive,
            send=send,
            params=path_params or {},
        )

        async def execute(connection):
            return await route["handler"](connection)

        try:
            await self.middleware.run(websocket, execute)
        except Exception as exc:
            await self._handle_websocket_exception(websocket, exc)
            return

        if not websocket.closed:
            await websocket.close()

    async def _handle_lifespan(self, receive, send):
        while True:
            message = await receive()
            message_type = message["type"]

            if message_type == "lifespan.startup":
                started = time.perf_counter()
                try:
                    for plugin in self.plugins:
                        await self._call_plugin_hook(plugin.startup, self)
                    for handler in self.startup_handlers:
                        await self._call_lifecycle_handler(handler)
                except Exception as exc:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        }
                    )
                    return

                self.state["startup_time_ms"] = round(
                    (time.perf_counter() - started) * 1000, 3
                )
                self.state["started_at"] = time.time()
                await send({"type": "lifespan.startup.complete"})
                continue

            if message_type == "lifespan.shutdown":
                try:
                    for handler in reversed(self.shutdown_handlers):
                        await self._call_lifecycle_handler(handler)
                    for plugin in reversed(self.plugins):
                        await self._call_plugin_hook(plugin.shutdown, self)
                except Exception as exc:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": str(exc),
                        }
                    )
                    return

                await send({"type": "lifespan.shutdown.complete"})
                return

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
            if isinstance(content, str):
                return Response(content, status_code=status_code, content_type="text/html; charset=utf-8")
            return JSONResponse(content, status_code=status_code)

        if isinstance(result, str):
            return Response(result, content_type="text/plain; charset=utf-8")

        if hasattr(result, "model_dump") or hasattr(result, "to_dict"):
            return JSONResponse(result)

        return JSONResponse(result)

    async def _send_error(self, send, exc):
        response = await self._build_error_response(exc)
        await self._send(send, response)

    async def _build_error_response(self, exc):
        if isinstance(exc, HTTPException):
            handler = self.exception_handlers.get(HTTPException)
            if handler:
                result = await self._call_exception_handler(handler, exc)
                return self._normalize_response(result)
            return JSONResponse(
                {"error": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers,
            )

        if isinstance(exc, ValidationError):
            handler = self.exception_handlers.get(ValidationError)
            if handler:
                result = await self._call_exception_handler(handler, exc)
                return self._normalize_response(result)
            return JSONResponse(
                {"error": "Validation Error", "detail": exc.errors()},
                status_code=422,
            )

        handler = self._find_exception_handler(exc)
        if handler:
            result = await self._call_exception_handler(handler, exc)
            return self._normalize_response(result)

        return JSONResponse({"error": "Internal Server Error"}, status_code=500)

    async def _handle_websocket_exception(self, websocket, exc):
        handler = self._find_exception_handler(exc)
        if handler:
            result = await self._call_exception_handler(handler, exc)
            if isinstance(result, dict):
                if not websocket.accepted:
                    await websocket.accept()
                await websocket.send_json(result)
                if not websocket.closed:
                    await websocket.close(code=1011)
                return

        if isinstance(exc, WebSocketException):
            if not websocket.closed:
                await websocket.close(code=exc.code, reason=exc.reason)
            return

        if not websocket.closed:
            await websocket.close(code=1011, reason="Internal Server Error")

    def _find_exception_handler(self, exc):
        for exc_type in type(exc).__mro__:
            handler = self.exception_handlers.get(exc_type)
            if handler:
                return handler
        return None

    async def _call_exception_handler(self, handler, exc):
        result = handler(exc)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _call_plugin_hook(self, hook, app):
        result = hook(app)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _call_lifecycle_handler(self, handler):
        result = handler()
        if inspect.isawaitable(result):
            return await result
        return result

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
