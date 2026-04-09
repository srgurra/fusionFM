from pathlib import Path

from .exceptions import HTTPException
from .http import Response
from .static import mount_static


def mount_spa(
    app,
    directory,
    mount_path="/app",
    assets_path="/assets",
    *,
    cache_assets_for=3600,
):
    root = Path(directory).resolve()
    assets_root = root / assets_path.strip("/")
    if assets_root.exists():
        mount_static(
            app,
            assets_root,
            url_path=f"{mount_path.rstrip('/')}/{assets_path.strip('/')}",
            cache_seconds=cache_assets_for,
        )

    async def spa_handler(request):
        index_path = root / "index.html"
        if not index_path.exists():
            raise HTTPException(404, "Frontend entrypoint not found")

        return Response(
            index_path.read_text(encoding="utf-8"),
            content_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get(mount_path.rstrip("/"))
    async def spa_root(request):
        return await spa_handler(request)

    @app.get(f"{mount_path.rstrip('/')}/{{path:path}}")
    async def spa_nested(request):
        return await spa_handler(request)
