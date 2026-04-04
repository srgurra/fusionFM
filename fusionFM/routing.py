import re

class Router:
    def __init__(self):
        self.routes = []

    def _compile_path(self, path):
        pattern = ""
        parts = path.strip("/").split("/")

        if path == "/":
            return re.compile(r"^/$")

        for part in parts:
            if part.startswith("{") and part.endswith("}"):
                name = part[1:-1]
                pattern += f"/(?P<{name}>[^/]+)"
            else:
                pattern += f"/{part}"

        return re.compile(f"^{pattern}/?$")

    def add_route(self, method, path, handler, model=None):
        method = method.upper()

        for route in self.routes:
            if route["method"] == method and route["raw_path"] == path:
                raise ValueError(f"Route already exists: {method} {path}")

        compiled = self._compile_path(path)

        self.routes.append(
            {
                "method": method,
                "raw_path": path,
                "pattern": compiled,
                "handler": handler,
                "model": model,
            }
        )

    def match(self, method, path):
        method = method.upper()

        for route in self.routes:
            if route["method"] != method:
                continue

            match = route["pattern"].match(path)
            if match:
                return route, match.groupdict()

        return None, None