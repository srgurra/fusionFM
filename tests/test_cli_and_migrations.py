from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine
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
    assert (project_root / "tests" / "test_app.py").exists()


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

    # Cleanup metadata registration for other tests
    Base.metadata.remove(Widget.__table__)
