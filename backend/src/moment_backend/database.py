from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_database(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def apply_migrations(engine) -> None:
    """Apply additive schema upgrades for the persistent SQLite archive.

    The project predates a migration framework. This deliberately idempotent
    upgrade lets existing data volumes acquire the new recording metadata while
    Base.metadata.create_all() continues to initialize fresh installations.
    """
    inspector = inspect(engine)
    if "recordings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("recordings")}
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        if "title" not in columns:
            _add_column(connection, "ALTER TABLE recordings ADD COLUMN title VARCHAR(100)")
        if "duration_ms" not in columns:
            _add_column(connection, "ALTER TABLE recordings ADD COLUMN duration_ms INTEGER")
        if "folder_id" not in columns:
            _add_column(connection, "ALTER TABLE recordings ADD COLUMN folder_id INTEGER")
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_recordings_folder_id ON recordings (folder_id)"))
        connection.execute(text("""
            INSERT OR IGNORE INTO schema_migrations (version)
            VALUES ('20260910_recording_metadata')
        """))


def _add_column(connection, statement: str) -> None:
    try:
        connection.execute(text(statement))
    except OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
