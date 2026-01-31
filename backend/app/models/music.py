"""
Music Task Model

Suno AI music generation with full pipeline support.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, Boolean, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class MusicTask(Base):
    """Music generation task (Suno AI integration)."""

    __tablename__ = "music_tasks"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Generation parameters
    prompt: Mapped[str] = mapped_column(Text)
    style: Mapped[Optional[str]] = mapped_column(String(1000))  # Extended for compiled prompts
    title: Mapped[Optional[str]] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(10), default="V5")  # V3_5, V4, V4_5, V5
    instrumental: Mapped[bool] = mapped_column(Boolean, default=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # States: pending → generating → downloading → completed | failed
    progress: Mapped[Optional[str]] = mapped_column(String(255))  # Human-readable status
    suno_task_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Result
    file_path: Mapped[Optional[str]] = mapped_column(String(500))  # Vault path
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))  # Suno CDN URL
    duration: Mapped[Optional[float]] = mapped_column(Float)  # Duration in seconds
    clip_id: Mapped[Optional[str]] = mapped_column(String(100))  # Suno clip ID
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Curation
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of tags

    # Attribution
    agent_id: Mapped[Optional[str]] = mapped_column(String(50))  # Which agent created it

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="music_tasks")

    def __repr__(self):
        return f"<MusicTask {self.id} - {self.status}>"
