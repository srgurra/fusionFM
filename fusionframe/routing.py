import re


class Router:
    def __init__(self):
        self.routes = []
        self._static_routes = {}
        self._dynamic_routes = {}
        self._wildcard_routes = {}

    def _normalize_path(self, path):
        if path == "/":
            return "/"
        normalized = path.rstrip("/")
        return normalized or "/"

    def _route_bucket_key(self, protocol, method):
        return (protocol.lower(), method.upper() if method else None)

    def _segment_count(self, path):
        normalized = self._normalize_path(path)
        if normalized == "/":
            return 0
        return len(normalized.strip("/").split("/"))

    def _has_params(self, path):
        return "{" in path and "}" in path

    def _has_path_wildcard(self, path):
        return ":path}" in path

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
                pattern += f"/{re.escape(part)}"

        return re.compile(f"^{pattern}/?$")

    def add_route(self, method, path, handler, model=None, protocol="http", name=None):
        method = method.upper() if method else None
        protocol = protocol.lower()
        normalized_path = self._normalize_path(path)
        bucket_key = self._route_bucket_key(protocol, method)

        for route in self.routes:
            if (
                route["protocol"] == protocol
                and route["method"] == method
                and route["raw_path"] == normalized_path
            ):
                route_name = method or protocol.upper()
                raise ValueError(f"Route already exists: {route_name} {normalized_path}")

        compiled = self._compile_path(normalized_path)

        route = {
            "protocol": protocol,
            "method": method,
            "raw_path": normalized_path,
            "pattern": compiled,
            "handler": handler,
            "model": model,
            "name": name or getattr(handler, "__name__", normalized_path),
            "deprecated": getattr(handler, "__fusionframe_deprecated__", False),
            "deprecation_reason": getattr(
                handler, "__fusionframe_deprecation_reason__", ""
            ),
            "deprecation_since": getattr(
                handler, "__fusionframe_deprecation_since__", None
            ),
        }

        self.routes.append(route)

        if not self._has_params(normalized_path):
            self._static_routes[(bucket_key, normalized_path)] = route
            return

        if self._has_path_wildcard(normalized_path):
            self._wildcard_routes.setdefault(bucket_key, []).append(route)
            return

        segment_count = self._segment_count(normalized_path)
        dynamic_bucket = self._dynamic_routes.setdefault(bucket_key, {})
        dynamic_bucket.setdefault(segment_count, []).append(route)

    def match(self, method, path, protocol="http"):
        method = method.upper() if method else None
        protocol = protocol.lower()
        normalized_path = self._normalize_path(path)
        bucket_key = self._route_bucket_key(protocol, method)

        static_match = self._static_routes.get((bucket_key, normalized_path))
        if static_match:
            return static_match, {}

        segment_count = self._segment_count(normalized_path)
        dynamic_candidates = self._dynamic_routes.get(bucket_key, {}).get(segment_count, [])
        for route in dynamic_candidates:
            match = route["pattern"].match(normalized_path)
            if match:
                return route, match.groupdict()

        for route in self._wildcard_routes.get(bucket_key, []):
            match = route["pattern"].match(normalized_path)
            if match:
                return route, match.groupdict()

        return None, None
