from __future__ import annotations

from moment_backend.app import create_app
from moment_backend.models import Recording
from conftest import make_config


def test_dashboard_requires_login_and_serves_exports(tmp_path):
    config = make_config(tmp_path)
    app = create_app(config)
    session_factory = app.config["moment_session_factory"]
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    (config.audio_dir / "complete.wav").write_bytes(b"RIFF")
    with session_factory() as database:
        recording = Recording(
            device_id="moment-001", original_filename="complete.wav", sha256="b" * 64,
            audio_path="complete.wav", status="completed", transcript="Transcript",
            notes_markdown="# Notes\n\n- <keep this safe>"
        )
        database.add(recording)
        database.commit()
        recording_id = recording.id

    client = app.test_client()
    assert client.get("/").status_code == 302
    assert client.post("/login", data={"password": "test-password"}).status_code == 302
    with client.session_transaction() as flask_session:
        csrf_token = flask_session["csrf_token"]
    assert client.get(f"/recordings/{recording_id}").status_code == 200
    assert client.get(f"/recordings/{recording_id}/transcript.txt").data == b"Transcript"
    pdf = client.get(f"/recordings/{recording_id}/notes.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"

    delete_response = client.post(
        f"/recordings/{recording_id}/delete",
        data={"csrf_token": csrf_token},
    )
    assert delete_response.status_code == 302
    assert not (config.audio_dir / "complete.wav").exists()

    with session_factory() as database:
        assert database.get(Recording, recording_id) is None

    assert client.get(f"/recordings/{recording_id}").status_code == 404
