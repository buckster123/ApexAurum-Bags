"""
AgentMemory Model - The Cortex

Persistent memory for agents across conversations.
Each agent remembers facts, preferences, and context per user.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AgentMemory(Base):
    """
    Per-agent, per-user memory storage.

    Memory types:
    - fact: Concrete information ("User's name is Alex", "Works in fintech")
    - preference: How user likes things ("Prefers concise answers", "Likes code examples")
    - context: Ongoing project/topic context ("Building a Vue.js app")
    - relationship: Agent-user dynamics ("User trusts for code review", "3rd conversation")
    """

    __tablename__ = "agent_memories"

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

    # Agent identifier: "AZOTH", "ELYSIAN-PAC", "custom_abc123", etc.
    agent_id: Mapped[str] = mapped_column(String(100), index=True)

    # Memory classification
    memory_type: Mapped[str] = mapped_column(String(20))  # fact, preference, context, relationship

    # Key-value storage
    key: Mapped[str] = mapped_column(String(255))  # "name", "prefers_code", "current_project"
    value: Mapped[str] = mapped_column(Text)  # The actual memory content

    # Confidence scoring (0.0 - 1.0)
    # Higher confidence = more reliable, prioritized in retrieval
    confidence: Mapped[float] = mapped_column(Float, default=0.8)

    # Source tracking (optional - which conversation did this come from)
    source_conversation_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    # Usage metrics - track how often this memory is used
    access_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user = relationship("User", backref="agent_memories")
    source_conversation = relationship("Conversation", backref="extracted_memories")

    # Composite indexes for efficient querying
    __table_args__ = (
        Index('idx_agent_memory_user_agent', 'user_id', 'agent_id'),
        Index('idx_agent_memory_lookup', 'user_id', 'agent_id', 'memory_type'),
    )

    def __repr__(self):
        return f"<AgentMemory {self.agent_id}:{self.key}={self.value[:20]}...>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "agent_id": self.agent_id,
            "memory_type": self.memory_type,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
        }
