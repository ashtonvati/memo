from __future__ import annotations

import pytest

from moment_backend.services import OpenRouterNotesGenerator, ProcessingError


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "# Notes\n\n- Follow up"}}]}


def test_openrouter_generator_uses_chat_completions(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("moment_backend.services.requests.post", fake_post)
    generator = OpenRouterNotesGenerator(
        "test-key", "google/gemini-2.5-flash-lite", "https://moment.example", "Moment"
    )

    assert generator.generate("Call the dentist.") == "# Notes\n\n- Follow up"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["HTTP-Referer"] == "https://moment.example"
    assert captured["json"]["model"] == "google/gemini-2.5-flash-lite"
    assert captured["json"]["messages"][0]["content"].endswith("Call the dentist.")


def test_openrouter_generator_requires_an_api_key():
    with pytest.raises(ProcessingError, match="OPENROUTER_API_KEY"):
        OpenRouterNotesGenerator("", "google/gemini-2.5-flash-lite").generate("A note")
