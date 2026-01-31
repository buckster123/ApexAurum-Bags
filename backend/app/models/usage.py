"""
Usage Counter Model - Granular per-resource usage tracking.

Tracks usage counters per user, per resource type, per billing period (YYYY-MM).
Uses PostgreSQL upsert for atomic increment operations.

Counter types:
- messages_haiku: Haiku model messages
- messages_sonnet: Sonnet model messages
- messages_opus: Opus model messages
- messages_other: Non-Anthropic or unclassified model messages
- suno_generations: Suno music generation requests
- council_sessions: Council deliberation sessions started
- jam_sessions: Jam collaboration sessions started
- nursery_training_jobs: Nursery fine-tuning jobs launched
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class UsageCounter(Base):
    """
    Per-user, per-resource, per-period usage counter.

    Designed for atomic upsert via PostgreSQL ON CONFLICT:
    - INSERT on first use in a period
    - UPDATE (increment count) on subsequent uses

    The unique constraint on (user_id, counter_type, period) enables
    the upsert pattern used by UsageService.increment_usage().
    """

    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint(
            'user_id', 'counter_type', 'period',
            name='uq_usage_counter_user_type_period'
        ),
        Index('idx_usage_user_period', 'user_id', 'period'),
        Index('idx_usage_user_type', 'user_id', 'counter_type'),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # User reference
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Counter identity
    counter_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    # Billing period in YYYY-MM format
    period: Mapped[str] = mapped_column(
        String(7),
        nullable=False
    )

    # Current count for this period
    count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Informational snapshot of the limit when counter was created
    limit_snapshot: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    def __repr__(self):
        return f"<UsageCounter {self.counter_type}={self.count} for user {self.user_id} ({self.period})>"
