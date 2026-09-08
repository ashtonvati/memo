from __future__ import annotations

import io
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
from .database import Base, create_database
from .models import Recording
from .storage import save_upload


def create_app(config: Config | None = None) -> Flask:
    config = config or Config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    engine, session_factory = create_database(config.database_url)
    Base.metadata.create_all(engine)

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key,
        MAX_CONTENT_LENGTH=config.max_upload_bytes,
        moment_config=config,
        moment_session_factory=session_factory,
    )

    @app.context_processor
    def template_context():
        return {"statuses": {"queued": "Queued", "transcribing": "Transcribing", "generating_notes": "Writing notes", "completed": "Ready", "failed": "Needs attention"}}

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
        with session_factory() as database:
            recordings = database.query(Recording).order_by(Recording.created_at.desc()).all()
        return render_template("index.html", recordings=recordings)

    @app.get("/recordings/<recording_id>")
    @login_required
    def recording_detail(recording_id: str):
        recording = _get_recording(recording_id)
        return render_template("recording.html", recording=recording)

    @app.get("/recordings/<recording_id>/audio")
    @login_required
    def recording_audio(recording_id: str):
        recording = _get_recording(recording_id)
        return send_from_directory(config.audio_dir, recording.audio_path, mimetype="audio/wav")

    @app.get("/recordings/<recording_id>/transcript.txt")
    @login_required
    def download_transcript(recording_id: str):
        recording = _get_recording(recording_id)
        if recording.transcript is None:
            abort(404)
        return current_app.response_class(
            recording.transcript,
            mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{recording_id}-transcript.txt"'},
        )

    @app.get("/recordings/<recording_id>/notes.md")
    @login_required
    def download_notes(recording_id: str):
        recording = _get_recording(recording_id)
        if recording.notes_markdown is None:
            abort(404)
        return current_app.response_class(
            recording.notes_markdown,
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{recording_id}-notes.md"'},
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
            output, as_attachment=True, download_name=f"{recording_id}-notes.pdf",
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
            database.commit()
            return {"id": recording.id, "status": recording.status, "duplicate": False}, 201

    return app


def _get_recording(recording_id: str) -> Recording:
    session_factory = current_app.config["moment_session_factory"]
    with session_factory() as database:
        recording = database.get(Recording, recording_id)
        if recording is None:
            abort(404)
        database.expunge(recording)
        return recording


def _verify_csrf() -> None:
    if not secrets.compare_digest(session.get("csrf_token", ""), request.form.get("csrf_token", "")):
        abort(400)


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
