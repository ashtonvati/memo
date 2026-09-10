from __future__ import annotations

from moment_backend.app import create_app
from moment_backend.models import Recording
from moment_backend.services import GeneratedRecording
from moment_backend.worker import claim_next, process_recording, recover_interrupted_jobs
from conftest import make_config


class FakeTranscriber:
    def transcribe(self, audio_path):
        assert audio_path.exists()
        return "Remember to order filters."


class FakeNotesGenerator:
    def generate(self, transcript):
        assert transcript == "Remember to order filters."
        return GeneratedRecording("Order coffee filters", "- Order filters")


def test_worker_transcribes_and_generates_notes(tmp_path):
    config = make_config(tmp_path)
    app = create_app(config)
    session_factory = app.config["moment_session_factory"]
    (config.audio_dir).mkdir(parents=True, exist_ok=True)
    (config.audio_dir / "one.wav").write_bytes(b"RIFF")
    with session_factory() as database:
        recording = Recording(
            device_id="moment-001", original_filename="one.wav", sha256="a" * 64,
            audio_path="one.wav", status="queued"
        )
        database.add(recording)
        database.commit()
        recording_id = recording.id

    assert claim_next(session_factory) == recording_id
    process_recording(recording_id, config, session_factory, FakeTranscriber(), FakeNotesGenerator())

    with session_factory() as database:
        completed = database.get(Recording, recording_id)
        assert completed.status == "completed"
        assert completed.transcript == "Remember to order filters."
        assert completed.title == "Order coffee filters"
        assert completed.notes_markdown == "- Order filters"


def test_worker_recovers_jobs_left_by_a_restart(tmp_path):
    config = make_config(tmp_path)
    app = create_app(config)
    session_factory = app.config["moment_session_factory"]
    with session_factory() as database:
        database.add(Recording(
            device_id="moment-001", original_filename="interrupted.wav", sha256="c" * 64,
            audio_path="interrupted.wav", status="generating_notes"
        ))
        database.commit()

    recover_interrupted_jobs(session_factory)
    with session_factory() as database:
        assert database.query(Recording).one().status == "queued"
