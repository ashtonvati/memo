from __future__ import annotations

import hashlib
import io
import wave

from moment_backend.app import create_app
from moment_backend.models import Recording
from conftest import make_config


def upload(client, payload: bytes):
    return client.post(
        "/api/v1/recordings",
        data={
            "audio": (io.BytesIO(payload), "recording_001.wav"),
            "device_id": "moment-001",
            "filename": "recording_001.wav",
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        headers={"Authorization": "Bearer test-device-token"},
        content_type="multipart/form-data",
    )


def test_upload_is_durable_and_idempotent(tmp_path):
    app = create_app(make_config(tmp_path))
    client = app.test_client()
    payload = b"RIFF" + b"\0" * 40

    first = upload(client, payload)
    assert first.status_code == 201
    assert first.json["status"] == "queued"
    assert (tmp_path / "audio" / f"{first.json['id']}.wav").read_bytes() == payload

    retry = upload(client, payload)
    assert retry.status_code == 200
    assert retry.json["duplicate"] is True
    assert retry.json["id"] == first.json["id"]


def test_upload_rejects_bad_checksum(tmp_path):
    app = create_app(make_config(tmp_path))
    client = app.test_client()
    response = client.post(
        "/api/v1/recordings",
        data={
            "audio": (io.BytesIO(b"RIFF"), "bad.wav"),
            "device_id": "moment-001",
            "filename": "bad.wav",
            "sha256": "0" * 64,
        },
        headers={"Authorization": "Bearer test-device-token"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_upload_stores_wav_duration(tmp_path):
    app = create_app(make_config(tmp_path))
    payload = io.BytesIO()
    with wave.open(payload, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        wav_file.writeframes(b"\0\0" * 12_000)

    response = upload(app.test_client(), payload.getvalue())
    with app.config["moment_session_factory"]() as database:
        recording = database.get(Recording, response.json["id"])
        assert recording.duration_ms == 1_500
