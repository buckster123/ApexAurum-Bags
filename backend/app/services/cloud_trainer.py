"""
CloudTrainerService - The Training Forge

Together.ai fine-tuning integration for the Nursery.
"The forge burns, and new minds emerge."
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

logger = logging.getLogger(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"

# Cost estimation data (approximate Together.ai pricing)
TRAINABLE_MODELS = {
    "meta-llama/Llama-3.2-1B-Instruct": {
        "label": "Llama 3.2 1B",
        "params": "1B",
        "lora_per_1k_tokens": 0.0002,
        "full_per_1k_tokens": 0.0005,
    },
    "meta-llama/Llama-3.2-3B-Instruct": {
        "label": "Llama 3.2 3B",
        "params": "3B",
        "lora_per_1k_tokens": 0.0004,
        "full_per_1k_tokens": 0.001,
    },
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Reference": {
        "label": "Llama 3.1 8B",
        "params": "8B",
        "lora_per_1k_tokens": 0.0008,
        "full_per_1k_tokens": 0.002,
    },
    "Qwen/Qwen2.5-7B-Instruct": {
        "label": "Qwen 2.5 7B",
        "params": "7B",
        "lora_per_1k_tokens": 0.0007,
        "full_per_1k_tokens": 0.0018,
    },
}

# Average tokens per training example (ChatML format)
AVG_TOKENS_PER_EXAMPLE = 800


class CloudTrainerService:
    """Together.ai fine-tuning integration."""

    @staticmethod
    async def upload_dataset(file_path: str, api_key: str) -> dict:
        """Upload JSONL dataset to Together.ai for fine-tuning.

        Returns: {"file_id": "file-xxx", "filename": "...", "bytes": N}
        """
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise ValueError("Dataset file is empty or missing")

        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    f"{TOGETHER_BASE_URL}/files",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (os.path.basename(file_path), f, "application/jsonl")},
                    data={"purpose": "fine-tune"},
                )

            if response.status_code != 200:
                error_detail = response.text[:500]
                logger.error(f"Together upload failed ({response.status_code}): {error_detail}")
                raise ValueError(f"Dataset upload failed: {response.status_code} - {error_detail}")

            data = response.json()
            return {
                "file_id": data.get("id"),
                "filename": data.get("filename"),
                "bytes": data.get("bytes", 0),
            }

    @staticmethod
    async def create_training_job(
        file_id: str,
        base_model: str,
        api_key: str,
        n_epochs: int = 3,
        learning_rate: float = 1e-5,
        lora: bool = True,
        suffix: str = None,
        batch_size: int = None,
    ) -> dict:
        """Start a fine-tuning job on Together.ai.

        Returns: {"job_id": "ft-xxx", "status": "pending", "output_name": "..."}
        """
        body = {
            "training_file": file_id,
            "model": base_model,
            "n_epochs": n_epochs,
            "learning_rate": learning_rate,
            "lora": lora,
            "train_on_inputs": "auto",
        }
        if suffix:
            body["suffix"] = suffix
        if batch_size:
            body["batch_size"] = batch_size

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{TOGETHER_BASE_URL}/fine-tunes",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code not in (200, 201):
                error_detail = response.text[:500]
                logger.error(f"Together create job failed ({response.status_code}): {error_detail}")
                raise ValueError(f"Job creation failed: {response.status_code} - {error_detail}")

            data = response.json()
            return {
                "job_id": data.get("id"),
                "status": _map_together_status(data.get("status", "")),
                "output_name": data.get("output_name"),
            }

    @staticmethod
    async def get_job_status(job_id: str, api_key: str) -> dict:
        """Get fine-tuning job status from Together.ai."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{TOGETHER_BASE_URL}/fine-tunes/{job_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if response.status_code != 200:
                raise ValueError(f"Status check failed: {response.status_code}")

            data = response.json()
            return {
                "job_id": data.get("id"),
                "status": _map_together_status(data.get("status", "")),
                "output_name": data.get("output_name"),
                "model": data.get("model"),
                "events": data.get("events", []),
                "training_file": data.get("training_file"),
            }

    @staticmethod
    async def list_jobs(api_key: str) -> list[dict]:
        """List fine-tuning jobs from Together.ai."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{TOGETHER_BASE_URL}/fine-tunes",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if response.status_code != 200:
                return []

            data = response.json()
            jobs = data if isinstance(data, list) else data.get("data", [])
            return [
                {
                    "job_id": j.get("id"),
                    "status": _map_together_status(j.get("status", "")),
                    "model": j.get("model"),
                    "output_name": j.get("output_name"),
                }
                for j in jobs
            ]

    @staticmethod
    async def cancel_job(job_id: str, api_key: str) -> dict:
        """Cancel a running fine-tuning job."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{TOGETHER_BASE_URL}/fine-tunes/{job_id}/cancel",
                headers={"Authorization": f"Bearer {api_key}"},
            )

            if response.status_code not in (200, 201):
                raise ValueError(f"Cancel failed: {response.status_code}")

            return {"cancelled": True, "job_id": job_id}

    @staticmethod
    def estimate_cost(
        num_examples: int,
        base_model: str,
        n_epochs: int = 3,
        lora: bool = True,
    ) -> dict:
        """Estimate training cost (local calculation, no API call).

        Returns cost estimate based on approximate Together.ai pricing.
        """
        model_info = TRAINABLE_MODELS.get(base_model)
        if not model_info:
            # Fallback: use 3B pricing
            model_info = TRAINABLE_MODELS["meta-llama/Llama-3.2-3B-Instruct"]

        total_tokens = num_examples * AVG_TOKENS_PER_EXAMPLE * n_epochs
        cost_per_1k = model_info["lora_per_1k_tokens"] if lora else model_info["full_per_1k_tokens"]
        estimated_cost = (total_tokens / 1000) * cost_per_1k

        # Rough time estimate (tokens per second varies by model)
        tokens_per_sec = 50000 if lora else 20000  # approximate
        estimated_minutes = max(1, total_tokens / tokens_per_sec / 60)

        return {
            "estimated_cost_usd": round(estimated_cost, 4),
            "total_tokens": total_tokens,
            "num_examples": num_examples,
            "n_epochs": n_epochs,
            "base_model": base_model,
            "model_label": model_info.get("label", base_model.split("/")[-1]),
            "lora": lora,
            "training_method": "LoRA" if lora else "Full fine-tune",
            "estimated_minutes": round(estimated_minutes, 1),
        }


def _map_together_status(together_status: str) -> str:
    """Map Together.ai status strings to our internal status values."""
    status_lower = together_status.lower().replace("status_", "")
    mapping = {
        "pending": "pending",
        "queued": "pending",
        "running": "running",
        "uploading": "uploading",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "failed",
        "canceled": "failed",
        "error": "failed",
    }
    return mapping.get(status_lower, "pending")


# ===============================================================================
# BACKGROUND AUTO-COMPLETION
# Fire-and-forget task for training job monitoring.
# ===============================================================================

async def auto_complete_training_job(job_db_id: str, user_id: str):
    """
    Background auto-completion for training jobs.

    Called via asyncio.create_task() after a training job is created.
    Polls Together.ai every 30s and updates DB status.
    On completion: creates NurseryModelRecord, posts Village event.

    Never raises -- failures update job status but don't crash the server.
    """
    # Import inside function to avoid circular imports
    from app.database import get_db_context
    from app.models.nursery import NurseryTrainingJob, NurseryModelRecord
    from app.models.user import User
    from app.models.billing import Subscription
    from app.services.provider_access import resolve_provider_access

    logger.info(f"Training auto-complete started for job {job_db_id}")

    try:
        async with get_db_context() as db:
            # Load the job
            result = await db.execute(
                select(NurseryTrainingJob)
                .where(NurseryTrainingJob.id == UUID(job_db_id))
            )
            job = result.scalar_one_or_none()

            if not job or not job.provider_job_id:
                logger.error(f"Training auto-complete: job {job_db_id} not found or no provider_job_id")
                return

            # Get user and resolve Together access
            user_result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = user_result.scalar_one_or_none()
            if not user:
                logger.error(f"Training auto-complete: user {user_id} not found")
                return

            sub_result = await db.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
            subscription = sub_result.scalar_one_or_none()
            tier = subscription.tier if subscription else "free_trial"

            access = await resolve_provider_access(user, "together", tier, db)
            if not access["allowed"]:
                job.status = "failed"
                job.error_message = "Together.ai access not available"
                await db.commit()
                return
            api_key = access["api_key"]
            if api_key is None:
                api_key = os.getenv("TOGETHER_API_KEY")
            if not api_key:
                job.status = "failed"
                job.error_message = "Together.ai API key not configured"
                await db.commit()
                return

            # ===========================================================
            # Poll for completion (every 30 seconds, max 2 hours)
            # ===========================================================
            max_wait = 7200  # 2 hours
            elapsed = 0
            poll_interval = 30

            while elapsed < max_wait:
                try:
                    status_data = await CloudTrainerService.get_job_status(
                        job.provider_job_id, api_key
                    )

                    poll_interval = 30  # Reset on success

                    new_status = status_data["status"]

                    # Update job in DB
                    job.status = new_status
                    if new_status == "running" and not job.started_at:
                        job.started_at = datetime.now(timezone.utc)

                    # Try to extract progress from events
                    events = status_data.get("events", [])
                    if events and new_status == "running":
                        # Use event count as rough progress indicator
                        job.progress = min(95.0, len(events) * 5.0)

                    await db.commit()

                    if new_status == "completed":
                        output_name = status_data.get("output_name")
                        logger.info(f"Training COMPLETED: job {job_db_id}, model: {output_name}")

                        # Mark job complete
                        job.completed_at = datetime.now(timezone.utc)
                        job.progress = 100.0
                        if output_name:
                            job.output_name = output_name

                        # Create NurseryModelRecord
                        model_record = NurseryModelRecord(
                            id=uuid4(),
                            user_id=UUID(user_id),
                            job_id=job.id,
                            name=output_name or f"model-{str(job.id)[:8]}",
                            base_model=job.base_model,
                            model_type="lora_adapter" if job.config and job.config.get("lora") else "cloud_hosted",
                            storage_path=output_name,  # Together hosts the model
                            capabilities=job.dataset.tool_names if job.dataset else [],
                            performance={"events_count": len(events)},
                            agent_id=job.agent_id,
                        )
                        db.add(model_record)
                        await db.commit()

                        # Update apprentice if job was started from auto_train
                        apprentice_id = job.config.get("apprentice_id") if job.config else None
                        if apprentice_id:
                            try:
                                from app.models.nursery import NurseryApprentice
                                ap_result = await db.execute(
                                    select(NurseryApprentice).where(NurseryApprentice.id == UUID(apprentice_id))
                                )
                                ap = ap_result.scalar_one_or_none()
                                if ap:
                                    ap.status = "trained"
                                    ap.model_id = model_record.id
                                    await db.commit()
                                    logger.info(f"Apprentice {apprentice_id} updated: status=trained, model_id={model_record.id}")
                            except Exception as ap_err:
                                logger.warning(f"Failed to update apprentice on completion: {ap_err}")

                        # Post Village event
                        try:
                            from app.services.village_events import get_village_broadcaster, VillageEvent, EventType
                            broadcaster = get_village_broadcaster()
                            event = VillageEvent(
                                type=EventType.TOOL_COMPLETE,
                                agent_id=job.agent_id or "SYSTEM",
                                zone="nursery",
                                message=f"Training complete: {output_name or 'new model'} ({job.base_model})",
                            )
                            await broadcaster.broadcast(event)
                        except Exception as ws_err:
                            logger.warning(f"Training auto-complete: broadcast failed (non-fatal): {ws_err}")

                        return

                    elif new_status == "failed":
                        job.completed_at = datetime.now(timezone.utc)
                        # Try to get error from events
                        error_msg = "Training failed on provider"
                        if events:
                            last_event = events[-1] if isinstance(events[-1], str) else events[-1].get("message", "")
                            if last_event:
                                error_msg = str(last_event)[:500]
                        job.error_message = error_msg
                        await db.commit()

                        # Update apprentice on failure
                        apprentice_id = job.config.get("apprentice_id") if job.config else None
                        if apprentice_id:
                            try:
                                from app.models.nursery import NurseryApprentice
                                ap_result = await db.execute(
                                    select(NurseryApprentice).where(NurseryApprentice.id == UUID(apprentice_id))
                                )
                                ap = ap_result.scalar_one_or_none()
                                if ap:
                                    ap.status = "failed"
                                    await db.commit()
                            except Exception as broadcast_err:
                                logger.warning(f"Village broadcast failed (non-fatal): {broadcast_err}")

                        logger.warning(f"Training FAILED: job {job_db_id}: {error_msg}")
                        return

                except Exception as poll_err:
                    error_str = str(poll_err)
                    if "429" in error_str or "rate" in error_str.lower():
                        poll_interval = min(poll_interval * 2, 300)
                        logger.warning(f"Together.ai rate limited, backing off to {poll_interval}s")
                    else:
                        logger.warning(f"Training poll error (will retry): {poll_err}")
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                    continue

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            # Timeout
            job.status = "failed"
            job.error_message = "Training timed out (2 hours)"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # Update apprentice on timeout
            apprentice_id = job.config.get("apprentice_id") if job.config else None
            if apprentice_id:
                try:
                    from app.models.nursery import NurseryApprentice
                    ap_result = await db.execute(
                        select(NurseryApprentice).where(NurseryApprentice.id == UUID(apprentice_id))
                    )
                    ap = ap_result.scalar_one_or_none()
                    if ap:
                        ap.status = "failed"
                        await db.commit()
                except Exception as broadcast_err:
                    logger.warning(f"Village broadcast failed (non-fatal): {broadcast_err}")

            logger.warning(f"Training TIMEOUT: job {job_db_id}")

    except Exception as e:
        logger.error(f"Training auto-complete FATAL: {e}")
        try:
            async with get_db_context() as db:
                result = await db.execute(
                    select(NurseryTrainingJob)
                    .where(NurseryTrainingJob.id == UUID(job_db_id))
                )
                job = result.scalar_one_or_none()
                if job:
                    job.status = "failed"
                    job.error_message = f"Internal error: {str(e)[:200]}"
                    job.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception as broadcast_err:
            logger.warning(f"Village broadcast failed (non-fatal): {broadcast_err}")
