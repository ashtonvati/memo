from __future__ import annotations

from werkzeug.security import generate_password_hash

from moment_backend.app import create_app
from moment_backend.config import Config


def make_config(tmp_path):
    config = Config()
    config.data_dir = tmp_path
    config.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    config.dashboard_password_hash = generate_password_hash("test-password")
    config.device_api_token = "test-device-token"
    config.secret_key = "test-session-secret"
    config.openrouter_api_key = "test-openrouter-key"
    config.openrouter_model = "notes-test"
    return config


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: API integration tests")
