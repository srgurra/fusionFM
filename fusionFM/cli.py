import os
import sys
from pathlib import Path

import click
import uvicorn

from .migrations import apply_migrations, generate_migration, init_migrations, load_app_module


@click.group()
def cli():
    """fusionFM command line interface."""
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
        load_app_module(app)
        migration_path = generate_migration(message=message, path=path)
    except Exception as e:
        raise click.ClickException(str(e))

    if migration_path is None:
        click.echo("No schema changes detected.")
        return

    click.echo(f"Created migration {migration_path}")


@cli.command("migrate")
@click.option("--path", default="migrations", show_default=True)
def migrate(path):
    try:
        applied = apply_migrations(path=path)
    except Exception as e:
        raise click.ClickException(str(e))

    if not applied:
        click.echo("No pending migrations.")
        return

    for migration in applied:
        click.echo(f"Applied {migration}")


@cli.command("scaffold")
@click.argument("name")
def scaffold(name):
    root = Path(name)
    files = {
        root / "app.py": (
            "from fusionFM import App\n\n"
            "app = App(title=\"fusionFM Project\")\n\n"
            "@app.get(\"/\")\n"
            "async def home(request):\n"
            "    return {\"message\": \"hello\"}\n"
        ),
        root / "templates" / ".gitkeep": "",
        root / "static" / ".gitkeep": "",
        root / "tests" / "test_app.py": (
            "from fusionFM import TestClient\n"
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
