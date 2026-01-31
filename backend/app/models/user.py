"""
User Model
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # JSON settings (preferences, UI state, etc.)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    # Admin flag (for coupon management, etc.)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Terms acceptance
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    knowledge = relationship("VillageKnowledge", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    music_tasks = relationship("MusicTask", back_populates="user", cascade="all, delete-orphan")

    # Billing & Monetization
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_balance = relationship("CreditBalance", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # The Vault - File Storage
    folders = relationship("Folder", back_populates="user", cascade="all, delete-orphan")
    files = relationship("File", back_populates="user", cascade="all, delete-orphan")

    # The Council - Deliberation Sessions
    deliberation_sessions = relationship("DeliberationSession", back_populates="user", cascade="all, delete-orphan")

    # The Nursery - Model Training Studio
    nursery_datasets = relationship("NurseryDataset", back_populates="user", cascade="all, delete-orphan")
    nursery_training_jobs = relationship("NurseryTrainingJob", back_populates="user", cascade="all, delete-orphan")
    nursery_models = relationship("NurseryModelRecord", back_populates="user", cascade="all, delete-orphan")
    nursery_apprentices = relationship("NurseryApprentice", back_populates="user", cascade="all, delete-orphan")

    # Devices (ApexPocket, etc.)
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")

    # The Remembering Deep - Vector Storage
    # TODO: Re-enable after fixing import order
    # vectors = relationship("UserVector", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<User {self.email}>"
