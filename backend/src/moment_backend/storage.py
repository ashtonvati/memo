from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO


def save_upload(source: BinaryIO, destination_dir: Path, recording_id: str) -> tuple[str, str]:
    """Stream an upload to durable storage and return its relative path and digest."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    temp_file = tempfile.NamedTemporaryFile(dir=destination_dir, delete=False, suffix=".part")
    try:
        with temp_file:
            while chunk := source.read(64 * 1024):
                digest.update(chunk)
                temp_file.write(chunk)
        filename = f"{recording_id}.wav"
        os.replace(temp_file.name, destination_dir / filename)
        return filename, digest.hexdigest()
    except Exception:
        Path(temp_file.name).unlink(missing_ok=True)
        raise
