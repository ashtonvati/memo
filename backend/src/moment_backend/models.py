from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


recording_tags = Table(
    "recording_tags",
    Base.metadata,
    Column("recording_id", String(36), ForeignKey("recordings.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(80), unique=True)
    recordings: Mapped[list["Recording"]] = relationship(back_populates="folder")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(80), unique=True)
    recordings: Mapped[list["Recording"]] = relationship(
        secondary=recording_tags, back_populates="tags"
    )


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    audio_path: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    folder: Mapped[Folder | None] = relationship(back_populates="recordings")
    tags: Mapped[list[Tag]] = relationship(secondary=recording_tags, back_populates="recordings")
