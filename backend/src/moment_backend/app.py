from __future__ import annotations

import io
import re
import secrets
from pathlib import Path
from xml.sax.saxutils import escape

from flask import Flask, abort, current_app, flash, redirect, render_template, request, send_file, send_from_directory, session, url_for
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from werkzeug.security import check_password_hash

from .auth import device_token_required, login_required
from .config import Config
from .database import Base, apply_migrations, create_database
from .models import Folder, Recording, Tag, recording_tags
from .storage import save_upload, wav_duration_ms
from sqlalchemy import or_
from sqlalchemy.orm import selectinload


def create_app(config: Config | None = None) -> Flask:
    config = config or Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    engine, session_factory = create_database(config.database_url)
    Base.metadata.create_all(engine)
    apply_migrations(engine)

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key,
        MAX_CONTENT_LENGTH=config.max_upload_bytes,
        moment_config=config,
        moment_session_factory=session_factory,
    )

    @app.context_processor
    def template_context():
        return {
            "statuses": {"queued": "Queued", "transcribing": "Transcribing", "generating_notes": "Writing notes", "completed": "Ready", "failed": "Needs attention"},
            "display_title": _display_title,
        }

    @app.template_filter("duration")
    def format_duration(duration_ms: int | None) -> str:
        if duration_ms is None:
            return "—"
        total_seconds = round(duration_ms / 1000)
        return f"{total_seconds // 60}:{total_seconds % 60:02d}"

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            password_hash = config.dashboard_password_hash
            if password_hash and check_password_hash(password_hash, request.form.get("password", "")):
                session.clear()
                session["authenticated"] = True
                session["csrf_token"] = secrets.token_urlsafe(24)
                return redirect(request.args.get("next") or url_for("index"))
            flash("Invalid password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        _verify_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        search = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        folder_id = _optional_int(request.args.get("folder"))
        tag_id = _optional_int(request.args.get("tag"))
        with session_factory() as database:
            query = database.query(Recording).options(
                selectinload(Recording.folder), selectinload(Recording.tags)
            )
            if search:
                pattern = f"%{search}%"
                query = query.filter(or_(Recording.title.ilike(pattern), Recording.transcript.ilike(pattern)))
            if status in {"queued", "transcribing", "generating_notes", "completed", "failed"}:
                query = query.filter(Recording.status == status)
            if folder_id is not None:
                query = query.filter(Recording.folder_id == folder_id)
            if tag_id is not None:
                query = query.join(Recording.tags).filter(Tag.id == tag_id)
            recordings = query.order_by(Recording.created_at.desc()).all()
            folders = database.query(Folder).order_by(Folder.name).all()
            tags = database.query(Tag).order_by(Tag.name).all()
        return render_template(
            "index.html", recordings=recordings, folders=folders, tags=tags,
            search=search, selected_status=status, selected_folder_id=folder_id,
            selected_tag_id=tag_id,
        )

    @app.get("/recordings/<recording_id>")
    @login_required
    def recording_detail(recording_id: str):
        recording = _get_recording(recording_id)
        selected_tag_ids = {tag.id for tag in recording.tags}
        with session_factory() as database:
            folders = database.query(Folder).order_by(Folder.name).all()
            tags = database.query(Tag).order_by(Tag.name).all()
        return render_template(
            "recording.html", recording=recording, folders=folders, tags=tags,
            selected_tag_ids=selected_tag_ids,
        )

    @app.get("/recordings/<recording_id>/audio")
    @login_required
    def recording_audio(recording_id: str):
        recording = _get_recording(recording_id)
        return send_from_directory(config.audio_dir, recording.audio_path, mimetype="audio/wav")

    @app.get("/recordings/<recording_id>/download")
    @login_required
    def download_audio(recording_id: str):
        recording = _get_recording(recording_id)
        return send_from_directory(
            config.audio_dir, recording.audio_path, mimetype="audio/wav", as_attachment=True,
            download_name=_download_name(recording, ".wav"),
        )

    @app.get("/recordings/<recording_id>/transcript.txt")
    @login_required
    def download_transcript(recording_id: str):
        recording = _get_recording(recording_id)
        if recording.transcript is None:
            abort(404)
        return send_file(
            io.BytesIO(recording.transcript.encode()), as_attachment=True,
            download_name=_download_name(recording, " - transcript.txt"), mimetype="text/plain",
        )

    @app.get("/recordings/<recording_id>/notes.md")
    @login_required
    def download_notes(recording_id: str):
        recording = _get_recording(recording_id)
        if recording.notes_markdown is None:
            abort(404)
        return send_file(
            io.BytesIO(recording.notes_markdown.encode()), as_attachment=True,
            download_name=_download_name(recording, " - notes.md"), mimetype="text/markdown",
        )

    @app.get("/recordings/<recording_id>/notes.pdf")
    @login_required
    def download_pdf(recording_id: str):
        recording = _get_recording(recording_id)
        if recording.notes_markdown is None:
            abort(404)
        output = io.BytesIO()
        _render_pdf(recording.notes_markdown, output)
        output.seek(0)
        return send_file(
            output, as_attachment=True, download_name=_download_name(recording, " - notes.pdf"),
            mimetype="application/pdf"
        )

    @app.post("/recordings/<recording_id>/delete")
    @login_required
    def delete_recording(recording_id: str):
        _verify_csrf()
        session_factory = current_app.config["moment_session_factory"]
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            if recording is None:
                abort(404)
            audio_path = config.audio_dir / recording.audio_path
            if recording.audio_path and audio_path.is_file():
                audio_path.unlink()
            database.delete(recording)
            database.commit()
        return redirect(url_for("index"))

    @app.post("/recordings/<recording_id>/title")
    @login_required
    def update_title(recording_id: str):
        _verify_csrf()
        title = _clean_name(request.form.get("title", ""), 100)
        if not title:
            abort(400, "A title is required.")
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            if recording is None:
                abort(404)
            recording.title = title
            database.commit()
        return redirect(url_for("recording_detail", recording_id=recording_id))

    @app.post("/recordings/<recording_id>/organization")
    @login_required
    def update_organization(recording_id: str):
        _verify_csrf()
        folder_id = _optional_int(request.form.get("folder_id"))
        tag_ids = {tag_id for value in request.form.getlist("tag_ids") if (tag_id := _optional_int(value)) is not None}
        with session_factory() as database:
            recording = database.get(Recording, recording_id)
            if recording is None:
                abort(404)
            recording.folder = database.get(Folder, folder_id) if folder_id is not None else None
            if folder_id is not None and recording.folder is None:
                abort(400, "Unknown folder.")
            tags = database.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
            if len(tags) != len(tag_ids):
                abort(400, "Unknown tag.")
            recording.tags = tags
            database.commit()
        return redirect(url_for("recording_detail", recording_id=recording_id))

    @app.post("/folders")
    @login_required
    def create_folder():
        _verify_csrf()
        _create_label(Folder, request.form.get("name", ""), session_factory)
        return redirect(url_for("index"))

    @app.post("/tags")
    @login_required
    def create_tag():
        _verify_csrf()
        _create_label(Tag, request.form.get("name", ""), session_factory)
        return redirect(url_for("index"))

    @app.post("/folders/<int:folder_id>/delete")
    @login_required
    def delete_folder(folder_id: int):
        _verify_csrf()
        with session_factory() as database:
            folder = database.get(Folder, folder_id)
            if folder is None:
                abort(404)
            database.query(Recording).filter(Recording.folder_id == folder_id).update({Recording.folder_id: None})
            database.delete(folder)
            database.commit()
        return redirect(url_for("index"))

    @app.post("/tags/<int:tag_id>/delete")
    @login_required
    def delete_tag(tag_id: int):
        _verify_csrf()
        with session_factory() as database:
            tag = database.get(Tag, tag_id)
            if tag is None:
                abort(404)
            database.execute(recording_tags.delete().where(recording_tags.c.tag_id == tag_id))
            database.delete(tag)
            database.commit()
        return redirect(url_for("index"))

    @app.post("/api/v1/recordings")
    @device_token_required
    def upload_recording():
        audio = request.files.get("audio")
        device_id = request.form.get("device_id", "").strip()
        filename = request.form.get("filename", "").strip()
        supplied_sha = request.form.get("sha256", "").lower().strip()
        if not audio or not device_id or not filename or len(supplied_sha) != 64:
            return {"error": "audio, device_id, filename, and a SHA-256 checksum are required"}, 400
        if Path(filename).suffix.lower() != ".wav":
            return {"error": "only WAV audio is accepted"}, 400
        with session_factory() as database:
            duplicate = database.query(Recording).filter_by(device_id=device_id, sha256=supplied_sha).first()
            if duplicate:
                return {"id": duplicate.id, "status": duplicate.status, "duplicate": True}, 200
            recording = Recording(
                device_id=device_id,
                original_filename=Path(filename).name,
                sha256=supplied_sha,
                audio_path="",
                status="queued",
            )
            database.add(recording)
            database.flush()
            stored_name, calculated_sha = save_upload(audio.stream, config.audio_dir, recording.id)
            if calculated_sha != supplied_sha:
                (config.audio_dir / stored_name).unlink(missing_ok=True)
                database.rollback()
                return {"error": "checksum mismatch"}, 400
            recording.audio_path = stored_name
            recording.duration_ms = wav_duration_ms(config.audio_dir / stored_name)
            database.commit()
            return {"id": recording.id, "status": recording.status, "duplicate": False}, 201

    return app


def _get_recording(recording_id: str) -> Recording:
    session_factory = current_app.config["moment_session_factory"]
    with session_factory() as database:
        recording = database.query(Recording).options(
            selectinload(Recording.folder), selectinload(Recording.tags)
        ).filter(Recording.id == recording_id).one_or_none()
        if recording is None:
            abort(404)
        database.expunge(recording)
        return recording


def _verify_csrf() -> None:
    if not secrets.compare_digest(session.get("csrf_token", ""), request.form.get("csrf_token", "")):
        abort(400)


def _display_title(recording: Recording) -> str:
    return recording.title or Path(recording.original_filename).stem


def _download_name(recording: Recording, suffix: str) -> str:
    base = _display_title(recording)
    base = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip(" .")[:100]
    return f"{base or 'recording'}{suffix}"


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _clean_name(value: str, maximum: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:maximum]


def _create_label(model, raw_name: str, session_factory) -> None:
    name = _clean_name(raw_name, 80)
    if not name:
        abort(400, "A name is required.")
    normalized_name = name.casefold()
    with session_factory() as database:
        if database.query(model).filter_by(normalized_name=normalized_name).first():
            abort(400, "That name already exists.")
        database.add(model(name=name, normalized_name=normalized_name))
        database.commit()


def _render_pdf(markdown: str, destination) -> None:
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(destination, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    story = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.2 * cm))
        elif line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["Heading2"]))
        else:
            story.append(Paragraph(escape(line.removeprefix("- ")), styles["BodyText"]))
    document.build(story)
