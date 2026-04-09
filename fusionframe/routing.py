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
                raw = part[1:-1]
                if ":" in raw:
                    name, converter = raw.split(":", 1)
                else:
                    name, converter = raw, "str"

                if converter == "path":
                    pattern += f"/(?P<{name}>.+)"
                else:
                    pattern += f"/(?P<{name}>[^/]+)"
            else:
                pattern += f"/{part}"

        return re.compile(f"^{pattern}/?$")

    def add_route(self, method, path, handler, model=None, protocol="http", name=None):
        method = method.upper() if method else None
        protocol = protocol.lower()

        for route in self.routes:
            if (
                route["protocol"] == protocol
                and route["method"] == method
                and route["raw_path"] == path
            ):
                route_name = method or protocol.upper()
                raise ValueError(f"Route already exists: {route_name} {path}")

        compiled = self._compile_path(path)

        self.routes.append(
            {
                "protocol": protocol,
                "method": method,
                "raw_path": path,
                "pattern": compiled,
                "handler": handler,
                "model": model,
                "name": name or getattr(handler, "__name__", path),
                "deprecated": getattr(handler, "__fusionframe_deprecated__", False),
                "deprecation_reason": getattr(
                    handler, "__fusionframe_deprecation_reason__", ""
                ),
                "deprecation_since": getattr(
                    handler, "__fusionframe_deprecation_since__", None
                ),
            }
        )

    def match(self, method, path, protocol="http"):
        method = method.upper() if method else None
        protocol = protocol.lower()

        for route in self.routes:
            if route["protocol"] != protocol:
                continue

            if route["method"] != method:
                continue

            match = route["pattern"].match(path)
            if match:
                return route, match.groupdict()

        return None, None
