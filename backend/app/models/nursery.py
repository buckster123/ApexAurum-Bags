"""
Nursery Models - The Growth Chamber

AI model training studio: datasets, training jobs, models, apprentices.
"The Village raises its own minds."
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Text, DateTime, Boolean, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class NurseryDataset(Base):
    """Training dataset for model fine-tuning."""

    __tablename__ = "nursery_datasets"

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

    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))  # synthetic, extracted, uploaded
    tool_names: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)  # list of tool names
    num_examples: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[Optional[str]] = mapped_column(String(500))
    agent_id: Mapped[Optional[str]] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    user = relationship("User", back_populates="nursery_datasets")
    training_jobs = relationship("NurseryTrainingJob", back_populates="dataset")
    apprentices = relationship("NurseryApprentice", back_populates="dataset")

    def __repr__(self):
        return f"<NurseryDataset {self.name} ({self.num_examples} examples)>"


class NurseryTrainingJob(Base):
    """Cloud training job tracked across providers."""

    __tablename__ = "nursery_training_jobs"

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
    dataset_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nursery_datasets.id", ondelete="CASCADE"),
        index=True
    )

    provider: Mapped[str] = mapped_column(String(50))  # together, vastai, runpod, replicate
    provider_job_id: Mapped[Optional[str]] = mapped_column(String(255))
    base_model: Mapped[str] = mapped_column(String(255))
    output_name: Mapped[Optional[str]] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # States: pending -> uploading -> running -> completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)

    config: Mapped[Optional[dict]] = mapped_column(JSONB)  # epochs, lr, lora_rank, etc.
    cost_estimate: Mapped[Optional[float]] = mapped_column(Float)
    cost_actual: Mapped[Optional[float]] = mapped_column(Float)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    agent_id: Mapped[Optional[str]] = mapped_column(String(50))

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    user = relationship("User", back_populates="nursery_training_jobs")
    dataset = relationship("NurseryDataset", back_populates="training_jobs")
    model = relationship("NurseryModelRecord", back_populates="training_job", uselist=False)

    def __repr__(self):
        return f"<NurseryTrainingJob {self.id} [{self.status}]>"


class NurseryModelRecord(Base):
    """Trained model metadata and references."""

    __tablename__ = "nursery_models"

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
    job_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nursery_training_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    base_model: Mapped[Optional[str]] = mapped_column(String(255))
    model_type: Mapped[str] = mapped_column(String(50))  # lora_adapter, cloud_hosted, uploaded

    storage_path: Mapped[Optional[str]] = mapped_column(String(500))
    capabilities: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)  # list of capabilities
    performance: Mapped[Optional[dict]] = mapped_column(JSONB)  # {final_loss, eval_metrics}

    agent_id: Mapped[Optional[str]] = mapped_column(String(50))
    village_posted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    user = relationship("User", back_populates="nursery_models")
    training_job = relationship("NurseryTrainingJob", back_populates="model")
    apprentices = relationship("NurseryApprentice", back_populates="model")

    def __repr__(self):
        return f"<NurseryModelRecord {self.name} ({self.model_type})>"


class NurseryApprentice(Base):
    """Agent-raised apprentice model."""

    __tablename__ = "nursery_apprentices"

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

    master_agent: Mapped[str] = mapped_column(String(50))  # AZOTH, ELYSIAN, etc.
    apprentice_name: Mapped[str] = mapped_column(String(255))
    specialization: Mapped[Optional[str]] = mapped_column(String(255))

    dataset_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nursery_datasets.id", ondelete="SET NULL"),
        nullable=True
    )
    model_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nursery_models.id", ondelete="SET NULL"),
        nullable=True
    )

    num_examples: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="dataset_ready")
    # States: dataset_ready -> training -> trained | failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    user = relationship("User", back_populates="nursery_apprentices")
    dataset = relationship("NurseryDataset", back_populates="apprentices")
    model = relationship("NurseryModelRecord", back_populates="apprentices")

    def __repr__(self):
        return f"<NurseryApprentice {self.apprentice_name} (master: {self.master_agent})>"
