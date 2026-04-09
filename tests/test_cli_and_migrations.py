from pathlib import Path

from click.testing import CliRunner

from fusionframe.cli import cli


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


def test_migrations_init_creates_alembic_environment(tmp_path):
    import fusionframe.migrations as migrations_module

    migrations_dir = tmp_path / "migrations"
    initialized = migrations_module.init_migrations(path=str(migrations_dir))

    assert initialized == migrations_dir
    assert (migrations_dir / "env.py").exists()
    assert (migrations_dir / "script.py.mako").exists()
    assert (migrations_dir / "versions").exists()
    assert (tmp_path / "alembic.ini").exists()
    assert "alembic" in (tmp_path / "alembic.ini").read_text(encoding="utf-8").lower()


def test_alembic_wrappers_and_cli_delegate_correctly(tmp_path, monkeypatch):
    import fusionframe.cli as cli_module
    import fusionframe.migrations as migrations_module

    calls = []

    class FakeRevision:
        path = "migrations/versions/0001_create_widgets.py"

    class FakeCommand:
        @staticmethod
        def revision(config, message, autogenerate):
            calls.append(
                (
                    "revision",
                    config.get_main_option("script_location"),
                    config.get_main_option("fusionframe.app_target"),
                    message,
                    autogenerate,
                )
            )
            return FakeRevision()

        @staticmethod
        def upgrade(config, revision):
            calls.append(
                (
                    "upgrade",
                    config.get_main_option("script_location"),
                    config.get_main_option("fusionframe.app_target"),
                    revision,
                )
            )

        @staticmethod
        def downgrade(config, revision):
            calls.append(
                (
                    "downgrade",
                    config.get_main_option("script_location"),
                    config.get_main_option("fusionframe.app_target"),
                    revision,
                )
            )

    class FakeConfig:
        def __init__(self, path):
            self.path = path
            self.options = {}

        def set_main_option(self, key, value):
            self.options[key] = value

        def get_main_option(self, key, default=None):
            return self.options.get(key, default)

    monkeypatch.setattr(
        migrations_module,
        "_get_alembic_api",
        lambda: (FakeCommand, FakeConfig),
    )
    monkeypatch.setattr(migrations_module, "load_app_module", lambda target: calls.append(("load", target)))
    monkeypatch.setattr(cli_module, "create_migration", migrations_module.create_migration)
    monkeypatch.setattr(cli_module, "apply_migrations", migrations_module.apply_migrations)
    monkeypatch.setattr(cli_module, "downgrade_migrations", migrations_module.downgrade_migrations)
    monkeypatch.setattr(cli_module, "init_migrations", migrations_module.init_migrations)

    revision = migrations_module.create_migration(
        app="example:app",
        message="create widgets",
        path=str(tmp_path / "migrations"),
    )
    upgraded = migrations_module.apply_migrations(
        app="example:app",
        path=str(tmp_path / "migrations"),
        revision="head",
    )
    downgraded = migrations_module.downgrade_migrations(
        app="example:app",
        path=str(tmp_path / "migrations"),
        revision="-1",
    )

    assert revision.path.endswith("create_widgets.py")
    assert upgraded == "head"
    assert downgraded == "-1"
    assert ("load", "example:app") in calls
    assert (
        "revision",
        str(tmp_path / "migrations"),
        "example:app",
        "create widgets",
        True,
    ) in calls
    assert ("upgrade", str(tmp_path / "migrations"), "example:app", "head") in calls
    assert ("downgrade", str(tmp_path / "migrations"), "example:app", "-1") in calls

    runner = CliRunner()
    init_result = runner.invoke(cli, ["migrations-init", "--path", str(tmp_path / "cli_migrations")])
    make_result = runner.invoke(
        cli,
        ["makemigration", "example:app", "--message", "create widgets", "--path", str(tmp_path / "cli_migrations")],
    )
    migrate_result = runner.invoke(
        cli,
        ["migrate", "example:app", "--path", str(tmp_path / "cli_migrations"), "--revision", "head"],
    )
    downgrade_result = runner.invoke(
        cli,
        ["downgrade", "example:app", "--path", str(tmp_path / "cli_migrations"), "--revision", "-1"],
    )

    assert init_result.exit_code == 0
    assert "Initialized migrations directory" in init_result.output
    assert make_result.exit_code == 0
    assert "Created Alembic revision" in make_result.output
    assert migrate_result.exit_code == 0
    assert "Applied Alembic upgrade to head" in migrate_result.output
    assert downgrade_result.exit_code == 0
    assert "Applied Alembic downgrade to -1" in downgrade_result.output


def test_migration_commands_require_alembic(tmp_path, monkeypatch):
    import fusionframe.migrations as migrations_module

    monkeypatch.setattr(
        migrations_module,
        "_get_alembic_api",
        lambda: (_ for _ in ()).throw(migrations_module.MigrationError("Alembic support requires the 'alembic' package.")),
    )
    monkeypatch.setattr(migrations_module, "load_app_module", lambda target: None)

    try:
        migrations_module.create_migration(
            app="example:app",
            message="create widgets",
            path=str(tmp_path / "migrations"),
        )
    except migrations_module.MigrationError as exc:
        assert "alembic" in str(exc).lower()
    else:
        raise AssertionError("expected missing alembic error")
