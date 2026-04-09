from pathlib import Path

from .exceptions import HTTPException
from .http import Response

CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}


def mount_static(app, directory, url_path="/static"):
    root = Path(directory).resolve()
    normalized_prefix = url_path.rstrip("/")

    @app.get(f"{normalized_prefix}/{{path:path}}")
    async def static_handler(request):
        relative_path = request.params["path"]
        file_path = (root / relative_path).resolve()

        if root not in file_path.parents and file_path != root:
            raise HTTPException(403, "Forbidden")

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(404, "Static file not found")

        content_type = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        return Response(
            file_path.read_bytes(),
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
