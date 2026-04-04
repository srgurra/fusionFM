import json
from urllib.parse import parse_qs


class Request:
    def __init__(self, scope, body=None, params=None):
        self.scope = scope
        self.method = scope["method"]
        self.path = scope["path"]
        self.params = params or {}
        self.body = body or {}
        self.query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        self.headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        self.state = {}
        self.user = None

    def get_header(self, name, default=None):
        return self.headers.get(name.lower(), default)


class Response:
    def __init__(self, content="", status_code=200, headers=None, content_type="text/plain; charset=utf-8"):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.content_type = content_type

    def render(self):
        if isinstance(self.content, bytes):
            return self.content
        if isinstance(self.content, str):
            return self.content.encode("utf-8")
        return str(self.content).encode("utf-8")


class JSONResponse(Response):
    def __init__(self, content, status_code=200, headers=None):
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            content_type="application/json",
        )

    def render(self):
        return json.dumps(self.content).encode("utf-8")