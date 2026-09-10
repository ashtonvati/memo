from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests


class ProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedRecording:
    title: str
    notes_markdown: str


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

    def generate(self, transcript: str) -> GeneratedRecording:
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
            "Create a factual 3 to 7 word title that helps its owner recognize the note at a glance. "
            "Write a short summary, action items when present, and key details in notes_markdown. "
            "Do not invent facts and do not duplicate the title as a Markdown heading.\n\nTranscript:\n" + transcript
        )
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "recording_notes",
                            "strict": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "notes_markdown": {"type": "string"},
                                },
                                "required": ["title", "notes_markdown"],
                                "additionalProperties": False,
                            },
                        },
                    },
                },
                timeout=300,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            generated = json.loads(content)
        except requests.RequestException as error:
            raise ProcessingError(f"OpenRouter request failed: {error}") from error
        except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as error:
            raise ProcessingError("OpenRouter returned an invalid completion response.") from error
        title = " ".join(str(generated.get("title", "")).split())
        notes = str(generated.get("notes_markdown", "")).strip()
        if not notes or not title or not 3 <= len(title.split()) <= 7 or len(title) > 100:
            raise ProcessingError("OpenRouter returned no generated notes.")
        return GeneratedRecording(title=title, notes_markdown=notes)
