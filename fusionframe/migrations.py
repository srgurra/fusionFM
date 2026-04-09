from __future__ import annotations

import hashlib
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
DOWNGRADE_POLICY = "fusionframe migrations are forward-only; write a manual corrective migration instead of downgrading."


class MigrationError(RuntimeError):
    pass


class MigrationDiffError(MigrationError):
    pass


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
    with engine.begin() as connection:
        columns = {col["name"] for col in inspect(connection).get_columns(SCHEMA_MIGRATIONS_TABLE)}
        if "checksum" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {SCHEMA_MIGRATIONS_TABLE} ADD COLUMN checksum TEXT"
                )
            )


def get_applied_migrations() -> dict[str, str | None]:
    ensure_migration_table()
    with engine.begin() as connection:
        rows = connection.execute(
            text(f"SELECT version, checksum FROM {SCHEMA_MIGRATIONS_TABLE}")
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_pending_migration_files(path: str = MIGRATIONS_DIR) -> list[Path]:
    migrations_path = init_migrations(path)
    applied = get_applied_migrations()

    files = sorted(file for file in migrations_path.glob("*.sql"))
    _validate_applied_checksums(files, applied)
    return [file for file in files if file.name not in applied]


def apply_migrations(path: str = MIGRATIONS_DIR) -> list[str]:
    pending_files = get_pending_migration_files(path)
    if not pending_files:
        return []

    applied = []
    ensure_migration_table()

    with engine.begin() as connection:
        for migration_file in pending_files:
            sql = migration_file.read_text(encoding="utf-8").strip()
            for statement in _split_sql_statements(sql):
                connection.execute(text(statement))
            connection.execute(
                text(
                    f"INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (version, checksum) VALUES (:version, :checksum)"
                ),
                {
                    "version": migration_file.name,
                    "checksum": _checksum_for_file(migration_file),
                },
            )
            applied.append(migration_file.name)

    return applied


def downgrade_migrations(*args, **kwargs):
    raise MigrationError(DOWNGRADE_POLICY)


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
    unsupported_changes = []

    for table in Base.metadata.sorted_tables:
        if table.name == SCHEMA_MIGRATIONS_TABLE:
            continue

        if table.name not in existing_tables:
            statements.append(str(CreateTable(table).compile(engine)).strip())
            continue

        database_columns = {
            column["name"]: column for column in inspector.get_columns(table.name)
        }
        metadata_columns = {column.name: column for column in table.columns}
        existing_columns = set(database_columns)
        for column in table.columns:
            if column.name in existing_columns:
                existing = database_columns[column.name]
                unsupported_changes.extend(
                    _compare_column_shape(table.name, column, existing)
                )
                continue

            compiled_column = CreateColumn(column).compile(dialect=engine.dialect)
            statements.append(
                f"ALTER TABLE {table.name} ADD COLUMN {compiled_column}".strip()
            )

        missing_columns = sorted(existing_columns - set(metadata_columns))
        if missing_columns:
            unsupported_changes.append(
                f"Table '{table.name}' has database columns not present in models: {', '.join(missing_columns)}"
            )

    existing_model_tables = {
        table.name for table in Base.metadata.sorted_tables if table.name != SCHEMA_MIGRATIONS_TABLE
    }
    removed_tables = sorted(existing_tables - existing_model_tables - {SCHEMA_MIGRATIONS_TABLE})
    if removed_tables:
        unsupported_changes.append(
            "Database has tables not present in models: "
            + ", ".join(removed_tables)
        )

    if unsupported_changes:
        raise MigrationDiffError(
            "Unsafe schema drift detected. fusionframe only auto-generates additive migrations. "
            + "Resolve these manually:\n- "
            + "\n- ".join(unsupported_changes)
        )

    return statements


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "migration"


def _checksum_for_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_applied_checksums(files, applied):
    for file in files:
        recorded = applied.get(file.name)
        if recorded and recorded != _checksum_for_file(file):
            raise MigrationError(
                f"Applied migration '{file.name}' no longer matches its recorded checksum. "
                "Create a new corrective migration instead of editing an applied one."
            )


def _split_sql_statements(sql: str) -> list[str]:
    statements = []
    for chunk in sql.split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


def _compare_column_shape(table_name: str, metadata_column, database_column) -> list[str]:
    issues = []
    model_type = str(metadata_column.type.compile(dialect=engine.dialect)).lower()
    database_type = str(database_column["type"]).lower()
    if model_type != database_type:
        issues.append(
            f"Column '{table_name}.{metadata_column.name}' type changed from '{database_type}' to '{model_type}'"
        )

    database_nullable = bool(database_column.get("nullable", True))
    if bool(metadata_column.nullable) != database_nullable:
        issues.append(
            f"Column '{table_name}.{metadata_column.name}' nullability changed from "
            f"{database_nullable} to {bool(metadata_column.nullable)}"
        )

    return issues
