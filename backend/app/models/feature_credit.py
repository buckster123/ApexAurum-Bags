"""
Feature Credit Models - Per-resource credit balances from pack purchases.

Tracks purchased credits (Opus messages, Suno generations, training jobs)
with per-purchase rows for auditable FIFO deduction and rollover expiry.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class FeatureCreditBalance(Base):
    """
    Per-purchase record of feature credits.

    Each purchase creates a new row with remaining balances.
    Credits expire at end of current month + 1 full month (rollover once).

    Pack types:
    - spark: User chooses ONE resource (50 Opus OR 20 Suno OR 2 training)
    - flame: Bundle (150 Opus + 50 Suno + 5 training)
    - inferno: Bundle (500 Opus + 200 Suno + 15 training)
    """

    __tablename__ = "feature_credit_balances"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pack_id: Mapped[str] = mapped_column(String(20), nullable=False)  # spark, flame, inferno
    resource_type: Mapped[Optional[str]] = mapped_column(String(30))  # For spark: which resource chosen

    # Remaining balances
    opus_messages: Mapped[int] = mapped_column(Integer, default=0)
    suno_generations: Mapped[int] = mapped_column(Integer, default=0)
    training_jobs: Mapped[int] = mapped_column(Integer, default=0)

    # Lifecycle
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stripe reference
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self):
        return f"<FeatureCreditBalance {self.pack_id} opus={self.opus_messages} suno={self.suno_generations} train={self.training_jobs} for user {self.user_id}>"
