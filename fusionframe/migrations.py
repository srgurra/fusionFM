from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

MIGRATIONS_DIR = "migrations"
ALEMBIC_INI = "alembic.ini"

ALEMBIC_ENV_TEMPLATE = """from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from fusionframe.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

app_target = config.get_main_option("fusionframe.app_target")
if app_target:
    module_name = app_target.split(":", 1)[0]
    __import__(module_name)

target_metadata = Base.metadata


def get_url():
    return os.getenv(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url", "sqlite:///fusionframe.db"),
    )


def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""

ALEMBIC_SCRIPT_TEMPLATE = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}


# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
'''


class MigrationError(RuntimeError):
    pass


def load_app_module(target: str):
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module_name = target.split(":", 1)[0]
    return importlib.import_module(module_name)


def init_migrations(path: str = MIGRATIONS_DIR, *, db_url: str | None = None) -> Path:
    migrations_path = Path(path)
    versions_path = migrations_path / "versions"
    migrations_path.mkdir(parents=True, exist_ok=True)
    versions_path.mkdir(parents=True, exist_ok=True)

    env_path = migrations_path / "env.py"
    if not env_path.exists():
        env_path.write_text(ALEMBIC_ENV_TEMPLATE, encoding="utf-8")

    script_template = migrations_path / "script.py.mako"
    if not script_template.exists():
        script_template.write_text(ALEMBIC_SCRIPT_TEMPLATE, encoding="utf-8")

    readme_path = migrations_path / "README"
    if not readme_path.exists():
        readme_path.write_text(
            "Alembic migration environment managed by fusionframe.\n",
            encoding="utf-8",
        )

    ini_path = _alembic_ini_path(migrations_path)
    if not ini_path.exists():
        ini_path.write_text(
            _render_alembic_ini(migrations_path, db_url=db_url),
            encoding="utf-8",
        )

    return migrations_path


def create_migration(message: str, *, app: str | None = None, path: str = MIGRATIONS_DIR, autogenerate: bool = True):
    if app:
        load_app_module(app)
    init_migrations(path)
    command, config_class = _get_alembic_api()
    config = _build_alembic_config(path, config_class, app=app)
    return command.revision(config, message=message, autogenerate=autogenerate)


def apply_migrations(*, app: str | None = None, path: str = MIGRATIONS_DIR, revision: str = "head"):
    if app:
        load_app_module(app)
    init_migrations(path)
    command, config_class = _get_alembic_api()
    config = _build_alembic_config(path, config_class, app=app)
    command.upgrade(config, revision)
    return revision


def downgrade_migrations(*, app: str | None = None, path: str = MIGRATIONS_DIR, revision: str = "-1"):
    if app:
        load_app_module(app)
    init_migrations(path)
    command, config_class = _get_alembic_api()
    config = _build_alembic_config(path, config_class, app=app)
    command.downgrade(config, revision)
    return revision


def _get_alembic_api():
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise MigrationError(
            "Alembic support requires the 'alembic' package. Install it with "
            "'pip install alembic' or add it to your project dependencies."
        ) from exc
    return command, Config


def _build_alembic_config(path: str, config_class, *, app: str | None = None):
    migrations_path = Path(path)
    ini_path = _alembic_ini_path(migrations_path)
    config = config_class(str(ini_path))
    config.set_main_option("script_location", str(migrations_path))
    if app:
        config.set_main_option("fusionframe.app_target", app)
    return config


def _alembic_ini_path(migrations_path: Path) -> Path:
    return migrations_path.parent / ALEMBIC_INI


def _render_alembic_ini(migrations_path: Path, *, db_url: str | None = None) -> str:
    default_url = db_url or os.getenv("DATABASE_URL", "sqlite:///fusionframe.db")
    return f"""[alembic]
script_location = {migrations_path}
prepend_sys_path = .
sqlalchemy.url = {default_url}
fusionframe.app_target =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
"""
