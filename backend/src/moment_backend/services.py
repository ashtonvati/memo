from __future__ import annotations

from pathlib import Path

import requests


class ProcessingError(RuntimeError):
    pass


class Transcriber:
    def __init__(self, model_name: str, device: str, compute_type: str) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def transcribe(self, audio_path: Path) -> str:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        segments, _ = self._model.transcribe(str(audio_path), vad_filter=True)
        return "\n".join(segment.text.strip() for segment in segments if segment.text.strip())


class OpenRouterNotesGenerator:
    def __init__(self, api_key: str, model: str, site_url: str = "", app_title: str = "Moment") -> None:
        self.api_key = api_key
        self.model = model
        self.site_url = site_url
        self.app_title = app_title

    def generate(self, transcript: str) -> str:
        if not self.api_key:
            raise ProcessingError("OpenRouter is not configured. Set OPENROUTER_API_KEY.")
        if not self.model:
            raise ProcessingError("OpenRouter is not configured. Set OPENROUTER_MODEL.")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self.app_title,
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        prompt = (
            "Turn this voice-note transcript into concise, useful Markdown notes. "
            "Use a title, a short summary, action items when present, and key details. "
            "Do not invent facts.\n\nTranscript:\n" + transcript
        )
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=300,
            )
            response.raise_for_status()
            notes = response.json()["choices"][0]["message"]["content"].strip()
        except requests.RequestException as error:
            raise ProcessingError(f"OpenRouter request failed: {error}") from error
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise ProcessingError("OpenRouter returned an invalid completion response.") from error
        if not notes:
            raise ProcessingError("OpenRouter returned no generated notes.")
        return notes
