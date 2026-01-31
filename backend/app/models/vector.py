"""
Vector Storage Model - The Remembering Deep

Semantic memory using pgvector for similarity search.
Each user has their own vector collections.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserVector(Base):
    """
    User vector storage for semantic search.

    Uses pgvector extension for efficient similarity search.
    Vectors are organized into collections per user.
    """

    __tablename__ = "user_vectors"

    # Identity
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Collection (allows organizing vectors)
    collection: Mapped[str] = mapped_column(
        String(100),
        default="default"
    )

    # Content and metadata
    content: Mapped[str] = mapped_column(Text)
    metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict
    )

    # Embedding is stored via raw SQL (pgvector type)
    # We don't map it directly since SQLAlchemy doesn't have native pgvector support
    # Access via raw queries

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    # Relationships - no back_populates to avoid circular dependency
    user = relationship("User")

    __table_args__ = (
        Index('idx_vectors_user_collection', 'user_id', 'collection'),
    )

    def __repr__(self):
        return f"<UserVector {self.id} - {self.collection}>"
