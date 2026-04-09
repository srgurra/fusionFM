class VersionedAPI:
    def __init__(self, app, version, prefix=""):
        version_str = str(version).lstrip("v")
        self.app = app
        self.prefix = f"{prefix}/v{version_str}".rstrip("/")

    def _path(self, path):
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.prefix}{path}"

    def get(self, path, **kwargs):
        return self.app.get(self._path(path), **kwargs)

    def post(self, path, **kwargs):
        return self.app.post(self._path(path), **kwargs)

    def put(self, path, **kwargs):
        return self.app.put(self._path(path), **kwargs)

    def delete(self, path, **kwargs):
        return self.app.delete(self._path(path), **kwargs)

    def websocket(self, path, **kwargs):
        return self.app.websocket(self._path(path), **kwargs)
