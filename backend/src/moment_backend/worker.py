from __future__ import annotations

import logging
import time

from sqlalchemy import update

from .config import Config
from .database import Base, apply_migrations, create_database
from .models import Recording
from .services import OpenRouterNotesGenerator, Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def claim_next(session_factory) -> str | None:
    with session_factory() as database:
        recording = database.query(Recording).filter_by(status="queued").order_by(Recording.created_at).first()
        if recording is None:
            return None
        recording.status = "transcribing"
        recording.attempts += 1
        recording.error_message = None
        database.commit()
        return recording.id


def recover_interrupted_jobs(session_factory) -> None:
    """Make jobs claimed by a stopped worker eligible after it restarts."""
    with session_factory() as database:
        database.execute(
            update(Recording)
            .where(Recording.status.in_(["transcribing", "generating_notes"]))
            .values(status="queued")
        )
        database.commit()


def process_recording(recording_id: str, config: Config, session_factory, transcriber, notes_generator) -> None:
    with session_factory() as database:
        recording = database.get(Recording, recording_id)
        if recording is None:
            return
        audio_path = config.audio_dir / recording.audio_path
    try:
        transcript = transcriber.transcribe(audio_path)
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            recording.transcript = transcript
            recording.status = "generating_notes"
            database.commit()
        generated = notes_generator.generate(transcript)
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            recording.title = generated.title
            recording.notes_markdown = generated.notes_markdown
            recording.status = "completed"
            database.commit()
    except Exception as error:
        logger.exception("Processing recording %s failed", recording_id)
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            recording.status = "failed"
            recording.error_message = str(error)
            database.commit()


def main() -> None:
    config = Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    engine, session_factory = create_database(config.database_url)
    Base.metadata.create_all(engine)
    apply_migrations(engine)
    recover_interrupted_jobs(session_factory)
    transcriber = Transcriber(config.whisper_model, config.whisper_device, config.whisper_compute_type)
    notes_generator = OpenRouterNotesGenerator(
        config.openrouter_api_key,
        config.openrouter_model,
        config.openrouter_site_url,
        config.openrouter_app_title,
    )
    while True:
        recording_id = claim_next(session_factory)
        if recording_id:
            process_recording(recording_id, config, session_factory, transcriber, notes_generator)
        else:
            time.sleep(config.worker_poll_seconds)


if __name__ == "__main__":
    main()
