import hashlib
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


def mount_static(app, directory, url_path="/static", *, cache_seconds=3600):
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

        content = file_path.read_bytes()
        etag = hashlib.sha256(content).hexdigest()
        if request.get_header("if-none-match") == etag:
            return Response(
                b"",
                status_code=304,
                headers={"ETag": etag, "Cache-Control": f"public, max-age={cache_seconds}"},
                content_type=CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
            )

        content_type = CONTENT_TYPES.get(
            file_path.suffix.lower(), "application/octet-stream"
        )
        return Response(
            content,
            content_type=content_type,
            headers={
                "Cache-Control": f"public, max-age={cache_seconds}",
                "ETag": etag,
            },
        )
