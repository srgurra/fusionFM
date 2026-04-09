from __future__ import annotations

import importlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn, CreateTable

from .db import Base, create_migration_table, engine

MIGRATIONS_DIR = "migrations"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"


def load_app_module(target: str):
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module_name = target.split(":", 1)[0]
    return importlib.import_module(module_name)


def init_migrations(path: str = MIGRATIONS_DIR) -> Path:
    migrations_path = Path(path)
    migrations_path.mkdir(parents=True, exist_ok=True)

    keep_file = migrations_path / ".gitkeep"
    if not keep_file.exists():
        keep_file.write_text("", encoding="utf-8")

    return migrations_path


def ensure_migration_table():
    create_migration_table()


def get_applied_migrations() -> set[str]:
    ensure_migration_table()
    with engine.begin() as connection:
        rows = connection.execute(
            text(f"SELECT version FROM {SCHEMA_MIGRATIONS_TABLE}")
        ).fetchall()
    return {row[0] for row in rows}


def get_pending_migration_files(path: str = MIGRATIONS_DIR) -> list[Path]:
    migrations_path = init_migrations(path)
    applied = get_applied_migrations()

    files = sorted(
        file
        for file in migrations_path.glob("*.sql")
        if file.name not in applied
    )
    return files


def apply_migrations(path: str = MIGRATIONS_DIR) -> list[str]:
    pending_files = get_pending_migration_files(path)
    if not pending_files:
        return []

    applied = []
    ensure_migration_table()

    with engine.begin() as connection:
        for migration_file in pending_files:
            sql = migration_file.read_text(encoding="utf-8").strip()
            if sql:
                connection.execute(text(sql))
            connection.execute(
                text(
                    f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version) VALUES (:version)"
                ),
                {"version": migration_file.name},
            )
            applied.append(migration_file.name)

    return applied


def generate_migration(message: str, path: str = MIGRATIONS_DIR) -> Path | None:
    migrations_path = init_migrations(path)
    statements = _build_schema_diff()
    if not statements:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    slug = _slugify(message or "migration")
    filename = f"{timestamp}_{slug}.sql"
    migration_path = migrations_path / filename
    migration_path.write_text(";\n\n".join(statements) + ";\n", encoding="utf-8")
    return migration_path


def _build_schema_diff() -> list[str]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    statements = []

    for table in Base.metadata.sorted_tables:
        if table.name == SCHEMA_MIGRATIONS_TABLE:
            continue

        if table.name not in existing_tables:
            statements.append(str(CreateTable(table).compile(engine)).strip())
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue

            compiled_column = CreateColumn(column).compile(dialect=engine.dialect)
            statements.append(
                f"ALTER TABLE {table.name} ADD COLUMN {compiled_column}".strip()
            )

    return statements


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "migration"
