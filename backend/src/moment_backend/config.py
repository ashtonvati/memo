from __future__ import annotations

import os
from pathlib import Path


class Config:
    """Environment-backed application configuration."""

    def __init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        self.database_url = os.getenv(
            "DATABASE_URL", f"sqlite:///{self.data_dir / 'moment.db'}"
        )
        self.secret_key = os.getenv("SECRET_KEY", "development-only-change-me")
        self.dashboard_password_hash = os.getenv("DASHBOARD_PASSWORD_HASH", "")
        self.device_api_token = os.getenv("DEVICE_API_TOKEN", "")
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
        self.whisper_model = os.getenv("WHISPER_MODEL", "small")
        self.whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
        self.whisper_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.getenv(
            "OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"
        )
        self.openrouter_site_url = os.getenv("OPENROUTER_SITE_URL", "")
        self.openrouter_app_title = os.getenv("OPENROUTER_APP_TITLE", "Moment")
        self.worker_poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"
