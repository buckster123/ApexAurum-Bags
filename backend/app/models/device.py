"""
Device Model - ApexPocket and future hardware devices.

Registered devices authenticate with long-lived API tokens (apex_dev_*)
instead of JWT. Each device is bound to a user account for billing.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class Device(Base):
    """Registered hardware device (ApexPocket, etc.)."""

    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # Owner
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Device info
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False, default="apex_pocket")

    # Authentication - hashed token (never store plaintext)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # First 13 chars for lookup

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, revoked

    # Soul state (synced from device via /pocket/sync)
    soul_state: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Device metadata
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship
    user = relationship("User", back_populates="devices")

    def __repr__(self):
        return f"<Device {self.device_name} ({self.device_type}) user={self.user_id}>"
