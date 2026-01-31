"""
ApexAurum Cloud - Error Log Model

GDPR-compliant error tracking. No PII stored:
- user_hash is SHA-256 of user_id + server salt (one-way)
- No IP addresses stored
- Messages sanitized to strip emails/tokens/passwords
- Auto-purged after configurable retention period
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Integer, Float, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class ErrorLog(Base):
    """Centralized error log entry. No PII - GDPR compliant."""

    __tablename__ = "error_logs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # Classification
    category: Mapped[str] = mapped_column(
        String(30), index=True
    )  # backend_exception, http_error, tool_failure, frontend_error, llm_error, webhook_error

    severity: Mapped[str] = mapped_column(
        String(10), index=True
    )  # warning, error, critical

    # Error details
    error_type: Mapped[str] = mapped_column(String(200))  # Exception class name
    message: Mapped[str] = mapped_column(Text)  # Sanitized error message
    stacktrace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Backend only, sanitized

    # Request context
    endpoint: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Anonymized user reference (SHA-256 hash, not reversible)
    user_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    # Structured metadata (tool_name, provider, model, etc.)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_error_logs_category_created", "category", "created_at"),
        Index("ix_error_logs_severity_created", "severity", "created_at"),
        Index("ix_error_logs_endpoint_created", "endpoint", "created_at"),
    )

    def __repr__(self):
        return f"<ErrorLog {self.category}/{self.severity}: {self.error_type}>"
