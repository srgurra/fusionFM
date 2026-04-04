import os
import sys
import click
import uvicorn


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