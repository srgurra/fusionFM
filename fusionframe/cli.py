import os
import sys
import subprocess
from pathlib import Path

import click
import uvicorn

from .migrations import (
    apply_migrations,
    create_migration,
    downgrade_migrations,
    init_migrations,
)


@click.group()
def cli():
    """fusionframe command line interface."""
    pass


@cli.command()
@click.argument("app")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--reload/--no-reload", default=True, show_default=True)
def run(app, host, port, reload):
    if ":" not in app:
        raise click.BadParameter("App must be in format module:object, e.g. example:app")

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=reload,
            reload_dirs=[cwd] if reload else None,
        )
    except Exception as e:
        raise click.ClickException(str(e))


@cli.command("migrations-init")
@click.option("--path", default="migrations", show_default=True)
def migrations_init(path):
    migrations_path = init_migrations(path)
    click.echo(f"Initialized migrations directory at {migrations_path}")


@cli.command("makemigration")
@click.argument("app")
@click.option("--message", "-m", default="migration", show_default=True)
@click.option("--path", default="migrations", show_default=True)
def makemigration(app, message, path):
    try:
        revision = create_migration(app=app, message=message, path=path)
    except Exception as e:
        raise click.ClickException(str(e))

    click.echo(f"Created Alembic revision {getattr(revision, 'path', revision)}")


@cli.command("migrate")
@click.argument("app")
@click.option("--path", default="migrations", show_default=True)
@click.option("--revision", default="head", show_default=True)
def migrate(app, path, revision):
    try:
        applied = apply_migrations(app=app, path=path, revision=revision)
    except Exception as e:
        raise click.ClickException(str(e))

    click.echo(f"Applied Alembic upgrade to {applied}")


@cli.command("downgrade")
@click.argument("app")
@click.option("--path", default="migrations", show_default=True)
@click.option("--revision", default="-1", show_default=True)
def downgrade(app, path, revision):
    try:
        applied = downgrade_migrations(app=app, path=path, revision=revision)
    except Exception as e:
        raise click.ClickException(str(e))

    click.echo(f"Applied Alembic downgrade to {applied}")


@cli.command("scaffold")
@click.argument("name")
def scaffold(name):
    root = Path(name)
    files = {
        root / "app.py": (
            "from fusionframe import App, AppSettings, auth_middleware, security_headers_middleware, session_middleware\n\n"
            "settings = AppSettings(title=\"fusionframe Project\")\n"
            "app = App(settings=settings)\n"
            "app.use(session_middleware(secure=False))\n"
            "app.use(security_headers_middleware)\n"
            "app.use(auth_middleware)\n\n"
            "@app.get(\"/\")\n"
            "async def home(request):\n"
            "    return {\"message\": \"hello\"}\n"
        ),
        root / "templates" / ".gitkeep": "",
        root / "static" / ".gitkeep": "",
        root / "frontend" / ".gitkeep": "",
        root / "tests" / "test_app.py": (
            "from fusionframe import TestClient\n"
            "from app import app\n\n"
            "def test_home():\n"
            "    client = TestClient(app)\n"
            "    response = client.get(\"/\")\n"
            "    assert response.status_code == 200\n"
        ),
    }

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    click.echo(f"Scaffolded project at {root}")


@cli.command("benchmark")
@click.option("--iterations", default=2000, show_default=True, type=int)
def benchmark(iterations):
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "FUSIONFRAME_BENCH_ITERATIONS": str(iterations)},
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(exc.stderr or str(exc))

    click.echo(result.stdout.strip())
