"""
Jam Session Models - The Athanor's Band Studio

Collaborative music creation where agents jam together.

Models:
- JamSession: The collaborative session with style, tempo, key
- JamParticipant: Agent roles in the session
- JamTrack: Each agent's contributed notes
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class JamMode(str, enum.Enum):
    """Jam session interaction modes."""
    CONDUCTOR = "conductor"  # User directs each agent
    JAM = "jam"              # Seeded auto-collaboration
    AUTO = "auto"            # Full creative freedom


class JamState(str, enum.Enum):
    """Jam session states."""
    FORMING = "forming"      # Setting up, assigning roles
    JAMMING = "jamming"      # Active contribution phase
    FINALIZING = "finalizing"  # Merging tracks, calling Suno
    COMPLETE = "complete"    # Done, music generated
    FAILED = "failed"        # Something went wrong


class JamRole(str, enum.Enum):
    """Musical roles for agents."""
    PRODUCER = "producer"    # Oversees, decides when to finalize (AZOTH)
    MELODY = "melody"        # Lead voice, main themes (ELYSIAN)
    BASS = "bass"            # Low-end foundation (VAJRA)
    HARMONY = "harmony"      # Chords, countermelodies (KETHER)
    RHYTHM = "rhythm"        # Percussion patterns
    FREE = "free"            # No specific role, contribute anything


# Default role assignments based on agent personality
DEFAULT_AGENT_ROLES = {
    "AZOTH": JamRole.PRODUCER,
    "ELYSIAN": JamRole.MELODY,
    "VAJRA": JamRole.BASS,
    "KETHER": JamRole.HARMONY,
}


class JamSession(Base):
    """
    A collaborative jam session where agents create music together.
    """
    __tablename__ = "jam_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Session metadata
    title: Mapped[str] = mapped_column(String(200), default="Untitled Jam")
    style: Mapped[Optional[str]] = mapped_column(Text)  # Target style for Suno
    tempo: Mapped[int] = mapped_column(Integer, default=120)  # BPM
    musical_key: Mapped[str] = mapped_column(String(20), default="C")  # C, Am, F#m, etc.
    time_signature: Mapped[str] = mapped_column(String(10), default="4/4")

    # Session state
    mode: Mapped[str] = mapped_column(String(20), default=JamMode.JAM.value)
    state: Mapped[str] = mapped_column(String(20), default=JamState.FORMING.value)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)

    # Inspiration/context
    inspiration: Mapped[Optional[str]] = mapped_column(Text)  # User prompt or search results
    village_memories_used: Mapped[Optional[str]] = mapped_column(Text)  # JSON of memory IDs

    # Final output
    final_midi_path: Mapped[Optional[str]] = mapped_column(Text)
    final_music_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    audio_influence: Mapped[float] = mapped_column(Float, default=0.5)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    participants: Mapped[List["JamParticipant"]] = relationship(
        "JamParticipant", back_populates="session", cascade="all, delete-orphan"
    )
    tracks: Mapped[List["JamTrack"]] = relationship(
        "JamTrack", back_populates="session", cascade="all, delete-orphan"
    )
    messages: Mapped[List["JamMessage"]] = relationship(
        "JamMessage", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<JamSession {self.id} '{self.title}' ({self.state})>"


class JamParticipant(Base):
    """
    An agent participating in a jam session with a specific role.
    """
    __tablename__ = "jam_participants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jam_sessions.id"), nullable=False
    )

    # Agent info
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=JamRole.FREE.value)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Contribution tracking
    contributions: Mapped[int] = mapped_column(Integer, default=0)
    total_notes: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    last_contribution_at: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    session: Mapped["JamSession"] = relationship("JamSession", back_populates="participants")

    def __repr__(self):
        return f"<JamParticipant {self.agent_id} ({self.role}) in {self.session_id}>"


class JamTrack(Base):
    """
    A single track of notes contributed by an agent.

    Notes are stored as JSON array:
    [
        {"note": "C4", "time": 0.0, "duration": 0.5, "velocity": 100},
        {"note": "E4", "time": 0.5, "duration": 0.5, "velocity": 100},
        ...
    ]
    """
    __tablename__ = "jam_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jam_sessions.id"), nullable=False
    )

    # Track metadata
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=JamRole.FREE.value)
    round_number: Mapped[int] = mapped_column(Integer, default=1)

    # Musical content
    notes: Mapped[dict] = mapped_column(JSON, default=list)  # Array of note objects
    description: Mapped[Optional[str]] = mapped_column(Text)  # Agent's description of contribution

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    session: Mapped["JamSession"] = relationship("JamSession", back_populates="tracks")

    def __repr__(self):
        return f"<JamTrack {self.agent_id} round {self.round_number} ({len(self.notes or [])} notes)>"


class JamMessage(Base):
    """
    Chat/deliberation messages during a jam session.

    Agents can discuss what they're doing, react to each other's contributions,
    suggest changes, etc.
    """
    __tablename__ = "jam_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jam_sessions.id"), nullable=False
    )

    # Message content
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="assistant")  # user/assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1)

    # Optional: Reference to track contribution made with this message
    track_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    session: Mapped["JamSession"] = relationship("JamSession", back_populates="messages")

    def __repr__(self):
        return f"<JamMessage {self.agent_id} round {self.round_number}>"
