from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from fusionframe.cli import cli
from fusionframe.db import Base
from fusionframe.orm import Model


def test_scaffold_command(tmp_path):
    project_root = tmp_path / "demo"

    result = CliRunner().invoke(cli, ["scaffold", str(project_root)])

    assert result.exit_code == 0
    assert (project_root / "app.py").exists()
    assert (project_root / "templates").exists()
    assert (project_root / "static").exists()
    assert (project_root / "frontend").exists()
    assert (project_root / "tests" / "test_app.py").exists()


def test_benchmark_command():
    result = CliRunner().invoke(cli, ["benchmark", "--iterations", "10"])

    assert result.exit_code == 0
    assert "requests_per_second" in result.output


def test_migration_generation_and_apply(tmp_path, monkeypatch):
    import fusionframe.db as db_module
    import fusionframe.migrations as migrations_module

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)
    monkeypatch.setattr(migrations_module, "engine", engine)

    class Widget(Model):
        __tablename__ = "widgets_test"

        name: Mapped[str] = mapped_column(nullable=False)

    migrations_dir = tmp_path / "migrations"
    migration_path = migrations_module.generate_migration(
        "create widgets",
        path=str(migrations_dir),
    )

    assert migration_path is not None
    assert migration_path.exists()
    assert "widgets_test" in migration_path.read_text(encoding="utf-8")

    applied = migrations_module.apply_migrations(path=str(migrations_dir))
    assert migration_path.name in applied

    migration_path.write_text("-- changed\n" + migration_path.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        migrations_module.get_pending_migration_files(path=str(migrations_dir))
    except RuntimeError as exc:
        assert "no longer matches its recorded checksum" in str(exc)
    else:
        raise AssertionError("expected checksum drift detection")

    # Cleanup metadata registration for other tests
    Base.metadata.remove(Widget.__table__)


def test_migration_diff_rejects_unsafe_column_drift(tmp_path, monkeypatch):
    import fusionframe.db as db_module
    import fusionframe.migrations as migrations_module

    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)
    monkeypatch.setattr(migrations_module, "engine", engine)

    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE accounts_drift (id INTEGER PRIMARY KEY, name INTEGER NOT NULL)")
        )

    class Account(Model):
        __tablename__ = "accounts_drift"
        name: Mapped[str] = mapped_column(nullable=False)

    try:
        migrations_module.generate_migration("unsafe drift", path=str(tmp_path / "migrations"))
    except migrations_module.MigrationDiffError as exc:
        message = str(exc)
        assert "Unsafe schema drift detected" in message
        assert "accounts_drift.name" in message
        assert "type changed" in message
    else:
        raise AssertionError("expected unsafe drift detection")

    Base.metadata.remove(Account.__table__)


def test_migration_diff_rejects_removed_schema_objects(tmp_path, monkeypatch):
    import fusionframe.db as db_module
    import fusionframe.migrations as migrations_module

    engine = create_engine(f"sqlite:///{tmp_path / 'removed.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)
    monkeypatch.setattr(migrations_module, "engine", engine)

    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE removed_cols (id INTEGER PRIMARY KEY, name TEXT NOT NULL, legacy TEXT)")
        )
        connection.execute(text("CREATE TABLE orphan_table (id INTEGER PRIMARY KEY)"))

    class RemovedCols(Model):
        __tablename__ = "removed_cols"
        name: Mapped[str] = mapped_column(nullable=False)

    try:
        migrations_module.generate_migration("removed schema", path=str(tmp_path / "migrations"))
    except migrations_module.MigrationDiffError as exc:
        message = str(exc)
        assert "database columns not present in models" in message
        assert "legacy" in message
        assert "Database has tables not present in models" in message
        assert "orphan_table" in message
    else:
        raise AssertionError("expected removed schema detection")

    Base.metadata.remove(RemovedCols.__table__)


def test_migrations_are_explicitly_forward_only():
    import fusionframe.migrations as migrations_module

    try:
        migrations_module.downgrade_migrations()
    except migrations_module.MigrationError as exc:
        assert "forward-only" in str(exc)
    else:
        raise AssertionError("expected forward-only downgrade policy")
