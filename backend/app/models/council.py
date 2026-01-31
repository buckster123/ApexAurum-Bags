"""
Council Models - The Deliberation Chamber

Database models for multi-agent deliberation sessions.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, Integer, Float, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeliberationSession(Base):
    """A multi-agent deliberation session."""
    __tablename__ = "deliberation_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    # Session info
    title: Mapped[Optional[str]] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(Text)  # The question being deliberated
    mode: Mapped[str] = mapped_column(String(20), default="manual")  # "manual" or "auto"
    state: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, paused, complete

    # Settings
    max_rounds: Mapped[int] = mapped_column(Integer, default=10)
    consensus_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    consensus_phrase: Mapped[Optional[str]] = mapped_column(String(100))  # e.g., "CONSENSUS REACHED"
    use_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str] = mapped_column(String(100), default="claude-haiku-4-5-20251001")  # Model for deliberation

    # Progress
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    convergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(50))

    # Human butt-in queue (consumed by next round)
    pending_human_message: Mapped[Optional[str]] = mapped_column(Text)

    # Cost tracking
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agents: Mapped[list["SessionAgent"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    rounds: Mapped[list["DeliberationRound"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    messages: Mapped[list["SessionMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    user: Mapped["User"] = relationship(back_populates="deliberation_sessions")


class SessionAgent(Base):
    """An agent participating in a deliberation session."""
    __tablename__ = "session_agents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("deliberation_sessions.id", ondelete="CASCADE"))

    # Agent info
    agent_id: Mapped[str] = mapped_column(String(50))  # AZOTH, VAJRA, ELYSIAN, KETHER, or custom ID
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    persona_override: Mapped[Optional[str]] = mapped_column(Text)  # Override system prompt for this session
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Mid-session join/leave tracking
    joined_at_round: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # Round when agent joined (0 = from start)
    left_at_round: Mapped[Optional[int]] = mapped_column(Integer)  # Round when agent left (None = still active)

    # Per-agent cost tracking
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    added_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    session: Mapped["DeliberationSession"] = relationship(back_populates="agents")


class DeliberationRound(Base):
    """A single round of deliberation."""
    __tablename__ = "deliberation_rounds"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("deliberation_sessions.id", ondelete="CASCADE"))

    round_number: Mapped[int] = mapped_column(Integer)

    # Human intervention
    human_message: Mapped[Optional[str]] = mapped_column(Text)  # Butt-in message

    # Analysis
    convergence_score: Mapped[float] = mapped_column(Float, default=0.0)
    key_agreements: Mapped[Optional[dict]] = mapped_column(JSON)  # [{topic, agents}]
    key_disagreements: Mapped[Optional[dict]] = mapped_column(JSON)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column()

    # Relationships
    session: Mapped["DeliberationSession"] = relationship(back_populates="rounds")
    messages: Mapped[list["SessionMessage"]] = relationship(back_populates="round")


class SessionMessage(Base):
    """A message in the deliberation (from agent or human)."""
    __tablename__ = "session_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("deliberation_sessions.id", ondelete="CASCADE"))
    round_id: Mapped[UUID] = mapped_column(ForeignKey("deliberation_rounds.id", ondelete="CASCADE"))

    # Message info
    role: Mapped[str] = mapped_column(String(20))  # "agent", "human", "system"
    agent_id: Mapped[Optional[str]] = mapped_column(String(50))  # For agent messages
    content: Mapped[str] = mapped_column(Text)

    # Tool usage
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON)
    tool_results: Mapped[Optional[dict]] = mapped_column(JSON)

    # Token tracking
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    session: Mapped["DeliberationSession"] = relationship(back_populates="messages")
    round: Mapped["DeliberationRound"] = relationship(back_populates="messages")


# Import User model for type hints (avoid circular import at runtime)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User
