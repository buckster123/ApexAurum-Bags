"""
Nursery API - The Growth Chamber

Training data management and Training Forge endpoints.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.rate_limit import limiter
from app.database import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.billing import Subscription
from app.models.nursery import NurseryModelRecord, NurseryTrainingJob, NurseryApprentice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nursery", tags=["Nursery"])


# Request schemas
class GenerateDataRequest(BaseModel):
    tool_names: list[str]
    num_examples: int = 50
    variation_level: str = "medium"
    dataset_name: Optional[str] = None


class ExtractDataRequest(BaseModel):
    tools_filter: Optional[list[str]] = None
    min_examples: int = 10
    dataset_name: Optional[str] = None


class EstimateRequest(BaseModel):
    dataset_id: str
    base_model: str = "meta-llama/Llama-3.2-3B-Instruct"
    n_epochs: int = 3
    lora: bool = True


class StartTrainingRequest(BaseModel):
    dataset_id: str
    base_model: str = "meta-llama/Llama-3.2-3B-Instruct"
    n_epochs: int = 3
    learning_rate: float = 1e-5
    lora: bool = True
    batch_size: Optional[int] = None
    suffix: Optional[str] = None
    apprentice_id: Optional[str] = None


class CreateApprenticeRequest(BaseModel):
    master_agent: str
    apprentice_name: str
    specialization: Optional[str] = None
    auto_generate: bool = False
    num_examples: int = 50
    variation_level: str = "medium"


async def _check_nursery_access(user: User, db: AsyncSession, require_training: bool = False):
    """Check if user has nursery access based on tier."""
    from app.config import TIER_LIMITS
    tier = "free_trial"
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription = result.scalar_one_or_none()
    if subscription:
        tier = subscription.tier
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])
    nursery_access = tier_config.get("nursery_access", False)

    if not nursery_access:
        raise HTTPException(
            status_code=403,
            detail="The Nursery requires Opus tier ($100/mo). Upgrade to access model training."
        )

    if require_training and nursery_access == "view_only":
        raise HTTPException(
            status_code=403,
            detail="Training requires Opus tier ($100/mo). Adept tier can browse the Data Garden."
        )


@router.get("/datasets")
async def list_datasets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's training datasets."""
    await _check_nursery_access(user, db)

    from app.services.nursery import NurseryService
    datasets = await NurseryService.list_datasets(str(user.id))
    return {"datasets": datasets, "count": len(datasets)}


@router.post("/datasets/generate")
@limiter.limit("5/minute")
async def generate_data(
    request: Request,
    body: GenerateDataRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate synthetic training data."""
    await _check_nursery_access(user, db, require_training=True)

    if not body.tool_names:
        raise HTTPException(status_code=400, detail="At least one tool name is required")

    if body.num_examples < 1 or body.num_examples > 500:
        raise HTTPException(status_code=400, detail="num_examples must be between 1 and 500")

    if body.variation_level not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="variation_level must be low, medium, or high")

    from app.services.nursery import NurseryService
    result = await NurseryService.generate_synthetic_data(
        tool_names=body.tool_names,
        num_examples=body.num_examples,
        variation_level=body.variation_level,
        user_id=str(user.id),
        dataset_name=body.dataset_name,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))

    return result


@router.post("/datasets/extract")
@limiter.limit("5/minute")
async def extract_data(
    request: Request,
    body: ExtractDataRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract training data from conversation history."""
    await _check_nursery_access(user, db, require_training=True)

    from app.services.nursery import NurseryService
    result = await NurseryService.extract_conversation_data(
        user_id=str(user.id),
        tools_filter=body.tools_filter,
        min_examples=body.min_examples,
        dataset_name=body.dataset_name,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Extraction failed"))

    return result


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dataset and its file."""
    await _check_nursery_access(user, db)

    from app.services.nursery import NurseryService
    deleted = await NurseryService.delete_dataset(dataset_id, str(user.id))

    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {"success": True, "message": "Dataset deleted"}


@router.get("/stats")
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get nursery statistics."""
    await _check_nursery_access(user, db)

    from app.services.nursery import NurseryService
    stats = await NurseryService.get_stats(str(user.id))
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING FORGE - Cloud fine-tuning endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/training/models")
async def list_trainable_models():
    """List available base models for fine-tuning."""
    from app.services.cloud_trainer import TRAINABLE_MODELS

    return {"models": [
        {"id": model_id, **info}
        for model_id, info in TRAINABLE_MODELS.items()
    ]}


@router.post("/training/estimate")
async def estimate_training_cost(
    request: EstimateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate the cost of a fine-tuning job."""
    await _check_nursery_access(user, db)

    from app.services.nursery import NurseryService
    from app.services.cloud_trainer import CloudTrainerService

    dataset = await NurseryService.get_dataset(request.dataset_id, str(user.id))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    num_examples = dataset.get("num_examples", 0)
    estimate = CloudTrainerService.estimate_cost(
        num_examples=num_examples,
        base_model=request.base_model,
        n_epochs=request.n_epochs,
        lora=request.lora,
    )

    return estimate


@router.post("/training/start")
@limiter.limit("3/minute")
async def start_training(
    request: Request,
    body: StartTrainingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a cloud fine-tuning job via Together.ai."""
    await _check_nursery_access(user, db, require_training=True)

    from app.services.nursery import NurseryService
    from app.services.cloud_trainer import CloudTrainerService, auto_complete_training_job
    from app.services.provider_access import resolve_provider_access

    # Get Together access (BYOK or platform grant)
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"

    access = await resolve_provider_access(user, "together", tier, db)
    if not access["allowed"]:
        raise HTTPException(
            status_code=400,
            detail="Together.ai access required. Configure a key in Settings or contact admin for platform access.",
        )
    api_key = access["api_key"]
    if api_key is None and access["allowed"]:
        import os
        api_key = os.getenv("TOGETHER_API_KEY")

    # Validate dataset
    dataset = await NurseryService.get_dataset(body.dataset_id, str(user.id))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Empty dataset validation
    if not dataset.get("num_examples") or dataset.get("num_examples", 0) < 1:
        raise HTTPException(status_code=400, detail="Dataset has 0 examples. Generate or extract data first.")

    num_examples = dataset.get("num_examples", 0)

    # Check concurrent job limit
    running_count_result = await db.execute(
        select(func.count(NurseryTrainingJob.id)).where(
            NurseryTrainingJob.user_id == user.id,
            NurseryTrainingJob.status.in_(["pending", "running", "uploading"]),
        )
    )
    running_count = running_count_result.scalar() or 0
    if running_count >= 3:
        raise HTTPException(
            status_code=429,
            detail="Maximum 3 concurrent training jobs. Wait for a job to complete or cancel one."
        )

    # Get cost estimate
    estimate = CloudTrainerService.estimate_cost(
        num_examples=num_examples,
        base_model=body.base_model,
        n_epochs=body.n_epochs,
        lora=body.lora,
    )

    # Upload dataset to Together
    storage_path = dataset.get("storage_path", "")
    file_id = await CloudTrainerService.upload_dataset(storage_path, api_key)

    # Create training job on Together
    job_info = await CloudTrainerService.create_training_job(
        file_id=file_id,
        base_model=body.base_model,
        api_key=api_key,
        n_epochs=body.n_epochs,
        learning_rate=body.learning_rate,
        lora=body.lora,
        suffix=body.suffix,
    )

    # Save job to DB
    config = {
        "n_epochs": body.n_epochs,
        "learning_rate": body.learning_rate,
        "lora": body.lora,
        "batch_size": body.batch_size,
        "suffix": body.suffix,
        "file_id": file_id,
    }
    if body.apprentice_id:
        config["apprentice_id"] = body.apprentice_id

    job = NurseryTrainingJob(
        id=uuid4(),
        user_id=user.id,
        dataset_id=UUID(body.dataset_id),
        provider="together",
        provider_job_id=job_info.get("job_id"),
        base_model=body.base_model,
        output_name=job_info.get("output_name"),
        status="running",
        progress=0.0,
        config=config,
        cost_estimate=estimate.get("estimated_cost_usd"),
        started_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    # Track training job usage
    try:
        from app.services.usage import UsageService
        usage_svc = UsageService(db)
        await usage_svc.increment_usage(user.id, "nursery_training_jobs")
    except Exception as e:
        logger.warning(f"Training job counter failed (non-fatal): {e}")

    # Update apprentice status if linked
    if body.apprentice_id:
        ap_result = await db.execute(
            select(NurseryApprentice).where(
                NurseryApprentice.id == UUID(body.apprentice_id),
                NurseryApprentice.user_id == user.id,
            )
        )
        ap = ap_result.scalar_one_or_none()
        if ap:
            ap.status = "training"
            await db.commit()

    # Fire background polling task
    asyncio.create_task(
        auto_complete_training_job(str(job.id), str(user.id))
    )

    return {
        "job_id": str(job.id),
        "provider_job_id": job_info.get("job_id"),
        "status": "running",
        "base_model": body.base_model,
        "output_name": job_info.get("output_name"),
        "estimated_cost": estimate.get("estimated_cost_usd"),
        "num_examples": num_examples,
        "n_epochs": body.n_epochs,
        "message": f"Training job started. Fine-tuning {body.base_model} with {num_examples} examples.",
    }


@router.get("/training/jobs")
async def list_training_jobs(
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List training jobs for the current user."""
    await _check_nursery_access(user, db)

    from app.models.nursery import NurseryTrainingJob

    query = (
        select(NurseryTrainingJob)
        .options(selectinload(NurseryTrainingJob.dataset))
        .where(NurseryTrainingJob.user_id == user.id)
    )

    if status:
        query = query.where(NurseryTrainingJob.status == status)

    query = query.order_by(NurseryTrainingJob.created_at.desc()).limit(50)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "count": len(jobs),
        "jobs": [
            {
                "id": str(j.id),
                "dataset_id": str(j.dataset_id),
                "dataset_name": j.dataset.name if j.dataset else "unknown",
                "provider": j.provider,
                "provider_job_id": j.provider_job_id,
                "base_model": j.base_model,
                "output_name": j.output_name,
                "status": j.status,
                "progress": j.progress,
                "cost_estimate": j.cost_estimate,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
    }


@router.get("/training/jobs/{job_id}")
async def get_training_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific training job."""
    await _check_nursery_access(user, db)

    from app.models.nursery import NurseryTrainingJob

    result = await db.execute(
        select(NurseryTrainingJob)
        .options(selectinload(NurseryTrainingJob.dataset))
        .where(
            NurseryTrainingJob.id == UUID(job_id),
            NurseryTrainingJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    return {
        "id": str(job.id),
        "dataset_id": str(job.dataset_id),
        "dataset_name": job.dataset.name if job.dataset else "unknown",
        "provider": job.provider,
        "provider_job_id": job.provider_job_id,
        "base_model": job.base_model,
        "output_name": job.output_name,
        "status": job.status,
        "progress": job.progress,
        "config": job.config,
        "cost_estimate": job.cost_estimate,
        "cost_actual": job.cost_actual,
        "error_message": job.error_message,
        "agent_id": job.agent_id,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.post("/training/jobs/{job_id}/cancel")
async def cancel_training_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running training job."""
    await _check_nursery_access(user, db, require_training=True)

    from app.models.nursery import NurseryTrainingJob
    from app.services.cloud_trainer import CloudTrainerService
    from app.api.v1.user import get_user_api_key

    result = await db.execute(
        select(NurseryTrainingJob).where(
            NurseryTrainingJob.id == UUID(job_id),
            NurseryTrainingJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    if job.status not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'. Only pending or running jobs can be cancelled.",
        )

    # Cancel on Together if we have the provider job ID
    if job.provider_job_id:
        api_key = get_user_api_key(user, "together")
        if api_key:
            try:
                await CloudTrainerService.cancel_job(job.provider_job_id, api_key)
            except Exception as e:
                logger.warning(f"Failed to cancel job on provider: {e}")

    job.status = "failed"
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.utcnow()

    return {
        "success": True,
        "job_id": str(job.id),
        "status": "failed",
        "message": "Training job cancelled.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL CRADLE + VILLAGE - Model management and Village integration
# ═══════════════════════════════════════════════════════════════════════════════


def _format_job_activity(job) -> str:
    model_label = job.base_model.split("/")[-1] if job.base_model else "unknown"
    status_msgs = {
        "completed": f"Training completed: {model_label}",
        "running": f"Training in progress: {model_label} ({job.progress or 0:.0f}%)",
        "failed": f"Training failed: {model_label}",
    }
    return status_msgs.get(job.status, f"Training {job.status}: {model_label}")


@router.get("/models")
async def list_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's trained models."""
    await _check_nursery_access(user, db)
    result = await db.execute(
        select(NurseryModelRecord)
        .options(selectinload(NurseryModelRecord.training_job))
        .where(NurseryModelRecord.user_id == user.id)
        .order_by(NurseryModelRecord.created_at.desc())
        .limit(50)
    )
    models = result.scalars().all()
    return {
        "count": len(models),
        "models": [
            {
                "id": str(m.id),
                "name": m.name,
                "base_model": m.base_model,
                "model_type": m.model_type,
                "storage_path": m.storage_path,
                "capabilities": m.capabilities or [],
                "performance": m.performance,
                "agent_id": m.agent_id,
                "village_posted": m.village_posted,
                "job_id": str(m.job_id) if m.job_id else None,
                "job_status": m.training_job.status if m.training_job else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ],
    }


@router.get("/discover")
async def discover_village_models(
    query: Optional[str] = None,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search Village for shared models."""
    await _check_nursery_access(user, db)
    from app.services.neural_memory import NeuralMemoryService
    neural = NeuralMemoryService(db)
    memories = await neural.get_village_memories(
        user_id=user.id,
        topic=query,
        limit=min(limit, 50),
        collection="nursery",
    )
    return {"count": len(memories), "models": memories, "query": query}


@router.get("/village-activity")
async def get_village_activity(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent nursery activity feed."""
    await _check_nursery_access(user, db)
    # Get recent jobs
    jobs_result = await db.execute(
        select(NurseryTrainingJob)
        .where(NurseryTrainingJob.user_id == user.id)
        .order_by(NurseryTrainingJob.created_at.desc())
        .limit(limit)
    )
    jobs = jobs_result.scalars().all()
    # Get recent models
    models_result = await db.execute(
        select(NurseryModelRecord)
        .where(NurseryModelRecord.user_id == user.id)
        .order_by(NurseryModelRecord.created_at.desc())
        .limit(limit)
    )
    models = models_result.scalars().all()
    # Merge into activity feed
    activity = []
    for j in jobs:
        activity.append({
            "type": "training_job",
            "id": str(j.id),
            "status": j.status,
            "base_model": j.base_model,
            "progress": j.progress,
            "agent_id": j.agent_id,
            "timestamp": (j.completed_at or j.started_at or j.created_at).isoformat() if (j.completed_at or j.started_at or j.created_at) else None,
            "message": _format_job_activity(j),
        })
    for m in models:
        activity.append({
            "type": "model_created",
            "id": str(m.id),
            "name": m.name,
            "base_model": m.base_model,
            "model_type": m.model_type,
            "village_posted": m.village_posted,
            "agent_id": m.agent_id,
            "timestamp": m.created_at.isoformat() if m.created_at else None,
            "message": f"Model '{m.name}' created ({m.model_type})" + (" — shared in Village" if m.village_posted else ""),
        })
    activity.sort(key=lambda a: a.get("timestamp") or "", reverse=True)
    return {"count": len(activity[:limit]), "activity": activity[:limit]}


@router.get("/models/{model_id}")
async def get_model_detail(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific model."""
    await _check_nursery_access(user, db)
    result = await db.execute(
        select(NurseryModelRecord)
        .options(selectinload(NurseryModelRecord.training_job))
        .where(NurseryModelRecord.id == UUID(model_id), NurseryModelRecord.user_id == user.id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    response = {
        "id": str(model.id), "name": model.name, "base_model": model.base_model,
        "model_type": model.model_type, "storage_path": model.storage_path,
        "capabilities": model.capabilities or [], "performance": model.performance,
        "agent_id": model.agent_id, "village_posted": model.village_posted,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }
    if model.training_job:
        j = model.training_job
        response["training_job"] = {
            "id": str(j.id), "provider": j.provider, "status": j.status,
            "base_model": j.base_model, "config": j.config,
            "cost_estimate": j.cost_estimate, "cost_actual": j.cost_actual,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
    return response


@router.post("/models/{model_id}/register")
async def register_model_in_village(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a model in the Village for sharing."""
    await _check_nursery_access(user, db, require_training=True)
    from app.services.neural_memory import NeuralMemoryService
    result = await db.execute(
        select(NurseryModelRecord).where(
            NurseryModelRecord.id == UUID(model_id),
            NurseryModelRecord.user_id == user.id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.village_posted:
        return {"success": True, "message": "Model already registered in the Village.", "already_posted": True}
    model.village_posted = True
    # Store in neural memory
    neural = NeuralMemoryService(db)
    capabilities_str = ", ".join(model.capabilities or []) or "general"
    memory_content = (
        f"Nursery model registered: {model.name}\n"
        f"Base: {model.base_model}\n"
        f"Type: {model.model_type}\n"
        f"Capabilities: {capabilities_str}\n"
        f"Performance: {model.performance or 'N/A'}"
    )
    await neural.store_message(
        user_id=user.id, content=memory_content,
        agent_id=model.agent_id or "NURSERY",
        role="assistant", visibility="village", collection="nursery",
    )
    await db.commit()
    # Broadcast Village event (non-fatal)
    try:
        from app.services.village_events import get_village_broadcaster, VillageEvent, EventType
        broadcaster = get_village_broadcaster()
        event = VillageEvent(
            type=EventType.TOOL_COMPLETE,
            agent_id=model.agent_id or "SYSTEM",
            zone="nursery",
            message=f"Model registered in Village: {model.name} ({model.base_model})",
        )
        await broadcaster.broadcast(event)
    except Exception as broadcast_err:
        logger.warning(f"Village broadcast failed (non-fatal): {broadcast_err}")
    return {"success": True, "model_id": str(model.id), "name": model.name, "message": f"Model '{model.name}' registered in the Village."}


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a model record."""
    await _check_nursery_access(user, db, require_training=True)
    result = await db.execute(
        select(NurseryModelRecord).where(
            NurseryModelRecord.id == UUID(model_id),
            NurseryModelRecord.user_id == user.id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    model_name = model.name
    await db.delete(model)
    await db.commit()
    return {"success": True, "message": f"Model '{model_name}' deleted."}


# ===============================================================================
# APPRENTICE PROTOCOL
# ===============================================================================

@router.get("/apprentices")
async def list_apprentices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's apprentices."""
    await _check_nursery_access(user, db)

    result = await db.execute(
        select(NurseryApprentice)
        .options(
            selectinload(NurseryApprentice.dataset),
            selectinload(NurseryApprentice.model),
        )
        .where(NurseryApprentice.user_id == user.id)
        .order_by(NurseryApprentice.created_at.desc())
        .limit(50)
    )
    apprentices = result.scalars().all()

    return {
        "count": len(apprentices),
        "apprentices": [
            {
                "id": str(a.id),
                "master_agent": a.master_agent,
                "apprentice_name": a.apprentice_name,
                "specialization": a.specialization,
                "status": a.status,
                "num_examples": a.num_examples,
                "dataset_id": str(a.dataset_id) if a.dataset_id else None,
                "dataset_name": a.dataset.name if a.dataset else None,
                "model_id": str(a.model_id) if a.model_id else None,
                "model_name": a.model.name if a.model else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in apprentices
        ],
    }


@router.post("/apprentices")
@limiter.limit("2/minute")
async def create_apprentice(
    request: Request,
    body: CreateApprenticeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an apprentice, optionally auto-generating a dataset."""
    await _check_nursery_access(user, db, require_training=True)

    valid_masters = {"AZOTH", "ELYSIAN", "VAJRA", "KETHER"}
    if body.master_agent not in valid_masters:
        raise HTTPException(status_code=400, detail=f"Invalid master_agent. Must be one of: {', '.join(sorted(valid_masters))}")

    if not body.apprentice_name or len(body.apprentice_name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Apprentice name must be at least 2 characters")

    apprentice = NurseryApprentice(
        id=uuid4(),
        user_id=user.id,
        master_agent=body.master_agent,
        apprentice_name=body.apprentice_name.strip(),
        specialization=body.specialization.strip() if body.specialization else None,
        status="dataset_ready",
    )

    # Optional: auto-generate training dataset
    if body.auto_generate:
        from app.services.nursery import NurseryService
        from app.tools import registry

        # Parse specialization as comma-separated tool names
        tool_names = []
        if body.specialization:
            tool_names = [t.strip() for t in body.specialization.split(",") if t.strip()]

        # Validate tool names
        all_tools = registry.get_all_tools()
        valid_tool_names = {t.schema.name for t in all_tools}
        tool_names = [t for t in tool_names if t in valid_tool_names]

        if not tool_names:
            # Fallback to common tools
            fallback = ["calculate", "web_search", "vault_list", "cortex_recall"]
            tool_names = [t for t in fallback if t in valid_tool_names]

        if tool_names:
            ds_name = f"apprentice_{body.apprentice_name.strip().lower().replace(' ', '_')}_{body.master_agent.lower()}"
            result = await NurseryService.generate_synthetic_data(
                tool_names=tool_names,
                num_examples=min(body.num_examples, 500),
                variation_level=body.variation_level,
                user_id=str(user.id),
                agent_id=body.master_agent,
                dataset_name=ds_name,
            )
            if result.get("success"):
                apprentice.dataset_id = UUID(result["dataset_id"])
                apprentice.num_examples = result["num_examples"]

    db.add(apprentice)
    await db.commit()

    response = {
        "id": str(apprentice.id),
        "master_agent": apprentice.master_agent,
        "apprentice_name": apprentice.apprentice_name,
        "specialization": apprentice.specialization,
        "status": apprentice.status,
        "num_examples": apprentice.num_examples,
        "dataset_id": str(apprentice.dataset_id) if apprentice.dataset_id else None,
        "message": f"Apprentice '{apprentice.apprentice_name}' created under {apprentice.master_agent}.",
    }
    if body.auto_generate and apprentice.dataset_id:
        response["message"] += f" Dataset generated with {apprentice.num_examples} examples."

    return response


@router.delete("/apprentices/{apprentice_id}")
async def delete_apprentice(
    apprentice_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an apprentice record."""
    await _check_nursery_access(user, db, require_training=True)

    result = await db.execute(
        select(NurseryApprentice).where(
            NurseryApprentice.id == UUID(apprentice_id),
            NurseryApprentice.user_id == user.id,
        )
    )
    apprentice = result.scalar_one_or_none()
    if not apprentice:
        raise HTTPException(status_code=404, detail="Apprentice not found")

    name = apprentice.apprentice_name
    await db.delete(apprentice)
    await db.commit()
    return {"success": True, "message": f"Apprentice '{name}' deleted."}
