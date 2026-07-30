from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_alembic_migration_creates_runtime_tables(tmp_path, monkeypatch):
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv(
        "APP_DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    config = Config("alembic.ini")
    config.set_main_option("script_location", "backend/alembic")

    command.upgrade(config, "head")

    tables = set(inspect(create_engine(f"sqlite:///{database_path.as_posix()}")).get_table_names())
    assert {
        "alembic_version",
        "sessions",
        "messages",
        "runs",
        "trace_events",
    } <= tables
    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    session_columns = {
        column["name"]: column for column in inspector.get_columns("sessions")
    }
    assert "profile_id" not in session_columns
    assert "context" in session_columns
    assert "profiles" not in tables
