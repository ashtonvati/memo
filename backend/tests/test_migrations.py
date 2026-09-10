from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from moment_backend.app import create_app
from conftest import make_config


def test_existing_database_receives_recording_metadata_columns(tmp_path):
    config = make_config(tmp_path)
    engine = create_engine(config.database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE recordings (
                id VARCHAR(36) PRIMARY KEY, device_id VARCHAR(128), original_filename VARCHAR(255),
                sha256 VARCHAR(64), audio_path VARCHAR(512), status VARCHAR(32), transcript TEXT,
                notes_markdown TEXT, error_message TEXT, attempts INTEGER, created_at DATETIME, updated_at DATETIME
            )
        """))

    create_app(config)

    columns = {column["name"] for column in inspect(engine).get_columns("recordings")}
    assert {"title", "duration_ms", "folder_id"} <= columns
    assert {"folders", "tags", "recording_tags"} <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM schema_migrations")).scalar_one() == "20260910_recording_metadata"
