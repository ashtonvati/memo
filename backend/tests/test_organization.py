from __future__ import annotations

from moment_backend.app import create_app
from moment_backend.models import Folder, Recording, Tag
from conftest import make_config


def test_recordings_can_be_organized_searched_and_renamed(tmp_path):
    app = create_app(make_config(tmp_path))
    session_factory = app.config["moment_session_factory"]
    with session_factory() as database:
        folder = Folder(name="Work", normalized_name="work")
        tag = Tag(name="Follow up", normalized_name="follow up")
        recording = Recording(
            device_id="moment-001", original_filename="one.wav", sha256="d" * 64,
            audio_path="one.wav", status="completed", title="Prepare project brief",
            transcript="Remember the customer interview.", folder=folder, tags=[tag],
        )
        database.add(recording)
        database.commit()
        recording_id, folder_id, tag_id = recording.id, folder.id, tag.id

    client = app.test_client()
    client.post("/login", data={"password": "test-password"})
    with client.session_transaction() as flask_session:
        csrf_token = flask_session["csrf_token"]

    selected_tag_page = client.get("/?q=customer&tag=" + str(tag_id))
    assert b"Prepare project brief" in selected_tag_page.data
    assert b'href="/?q=customer"' in selected_tag_page.data
    assert client.post(
        f"/recordings/{recording_id}/title",
        data={"csrf_token": csrf_token, "title": "Customer interview actions"},
    ).status_code == 302
    assert client.post(
        f"/recordings/{recording_id}/organization",
        data={"csrf_token": csrf_token, "folder_id": str(folder_id), "tag_ids": [str(tag_id)]},
    ).status_code == 302
    assert client.post(
        f"/folders/{folder_id}/delete", data={"csrf_token": csrf_token}
    ).status_code == 302
    assert client.post(
        f"/tags/{tag_id}/delete", data={"csrf_token": csrf_token}
    ).status_code == 302
    with session_factory() as database:
        recording = database.get(Recording, recording_id)
        assert recording.title == "Customer interview actions"
        assert recording.folder is None
        assert recording.tags == []
