"""
Tier 15: Nursery Tools - The Data Garden

Training data generation and dataset management.
"From data, new minds are born."
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory
from app.config import get_settings

logger = logging.getLogger(__name__)


class NurseryGenerateDataTool(BaseTool):
    """Generate synthetic training data for specified tools."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_generate_data",
            description="""Generate synthetic training data for model fine-tuning.

Creates ChatML-format JSONL training examples by analyzing tool schemas
and generating varied user queries paired with correct tool calls.

Use to:
- Create training data for specific tools
- Build datasets for model fine-tuning
- Prepare data for the Training Forge

Variation levels: low (simple), medium (natural), high (diverse).
Returns dataset ID and metadata.""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool names to generate data for (e.g., ['calculator', 'web_search'])",
                    },
                    "num_examples": {
                        "type": "integer",
                        "description": "Number of examples to generate (default: 50)",
                        "default": 50,
                    },
                    "variation_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Query variation level",
                        "default": "medium",
                    },
                    "dataset_name": {
                        "type": "string",
                        "description": "Custom name for the dataset (optional)",
                    },
                },
                "required": ["tool_names"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        tool_names = params.get("tool_names", [])
        if not tool_names:
            return ToolResult(success=False, error="At least one tool name is required")

        num_examples = min(params.get("num_examples", 50), 500)  # Cap at 500
        variation_level = params.get("variation_level", "medium")
        dataset_name = params.get("dataset_name")

        try:
            from app.services.nursery import NurseryService

            result = await NurseryService.generate_synthetic_data(
                tool_names=tool_names,
                num_examples=num_examples,
                variation_level=variation_level,
                user_id=str(context.user_id),
                agent_id=context.agent_id,
                dataset_name=dataset_name,
            )

            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error", "Generation failed"))

            return ToolResult(
                success=True,
                result={
                    "dataset_id": result["dataset_id"],
                    "name": result["name"],
                    "num_examples": result["num_examples"],
                    "size_kb": round(result["size_bytes"] / 1024, 1),
                    "tools": result["tools"],
                    "message": f"Generated {result['num_examples']} training examples for {', '.join(tool_names)}",
                },
            )

        except Exception as e:
            logger.exception("Nursery generate data error")
            return ToolResult(success=False, error=f"Failed to generate data: {str(e)}")


class NurseryExtractDataTool(BaseTool):
    """Extract training data from conversation history."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_extract_data",
            description="""Extract training data from your conversation history.

Mines real tool usage from past chats - finds messages where tools
were called and pairs them with the user query that triggered them.

Use to:
- Mine real-world tool usage patterns
- Create datasets from actual conversations
- Build training data from authentic interactions

Returns dataset with deduplicated examples in ChatML JSONL format.""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "tools_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only extract calls to these tools (optional, extracts all if omitted)",
                    },
                    "min_examples": {
                        "type": "integer",
                        "description": "Minimum examples required (default: 10)",
                        "default": 10,
                    },
                    "dataset_name": {
                        "type": "string",
                        "description": "Custom name for the dataset (optional)",
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        tools_filter = params.get("tools_filter")
        min_examples = params.get("min_examples", 10)
        dataset_name = params.get("dataset_name")

        try:
            from app.services.nursery import NurseryService

            result = await NurseryService.extract_conversation_data(
                user_id=str(context.user_id),
                tools_filter=tools_filter,
                min_examples=min_examples,
                agent_id=context.agent_id,
                dataset_name=dataset_name,
            )

            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error", "Extraction failed"))

            return ToolResult(
                success=True,
                result={
                    "dataset_id": result["dataset_id"],
                    "name": result["name"],
                    "num_examples": result["num_examples"],
                    "size_kb": round(result["size_bytes"] / 1024, 1),
                    "tools_extracted": result.get("tools_extracted", {}),
                    "message": f"Extracted {result['num_examples']} examples from conversation history",
                },
            )

        except Exception as e:
            logger.exception("Nursery extract data error")
            return ToolResult(success=False, error=f"Failed to extract data: {str(e)}")


class NurseryListDatasetsTool(BaseTool):
    """List available training datasets."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_list_datasets",
            description="""List your training datasets in the Nursery.

Shows all datasets with name, source (synthetic/extracted),
tool coverage, example count, and size.

Use to:
- See available training data
- Check dataset sizes before training
- Find datasets for specific tools""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        try:
            from app.services.nursery import NurseryService

            datasets = await NurseryService.list_datasets(str(context.user_id))

            limit = min(params.get("limit", 20), 50)
            datasets = datasets[:limit]

            return ToolResult(
                success=True,
                result={
                    "count": len(datasets),
                    "datasets": datasets,
                },
            )

        except Exception as e:
            logger.exception("Nursery list datasets error")
            return ToolResult(success=False, error=f"Failed to list datasets: {str(e)}")


class NurseryEstimateCostTool(BaseTool):
    """Estimate the cost of fine-tuning a model on a dataset."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_estimate_cost",
            description="""Estimate the cost of fine-tuning a model on a Nursery dataset.

Returns estimated cost, training time, and resource breakdown based on
dataset size, model, and training configuration.

Use to:
- Check cost before starting a training job
- Compare costs across different models or configs
- Plan training budget""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "description": "ID of the dataset to train on",
                    },
                    "base_model": {
                        "type": "string",
                        "description": "Base model for fine-tuning (default: meta-llama/Llama-3.2-3B-Instruct)",
                        "default": "meta-llama/Llama-3.2-3B-Instruct",
                    },
                    "n_epochs": {
                        "type": "integer",
                        "description": "Number of training epochs (default: 3)",
                        "default": 3,
                    },
                    "lora": {
                        "type": "boolean",
                        "description": "Use LoRA (parameter-efficient) training (default: true)",
                        "default": True,
                    },
                },
                "required": ["dataset_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        dataset_id = params.get("dataset_id")
        base_model = params.get("base_model", "meta-llama/Llama-3.2-3B-Instruct")
        n_epochs = params.get("n_epochs", 3)
        lora = params.get("lora", True)

        try:
            from app.services.nursery import NurseryService
            from app.services.cloud_trainer import CloudTrainerService

            dataset = await NurseryService.get_dataset(dataset_id, str(context.user_id))
            if not dataset:
                return ToolResult(success=False, error="Dataset not found")

            num_examples = dataset.get("num_examples", 0)
            estimate = CloudTrainerService.estimate_cost(
                num_examples=num_examples,
                base_model=base_model,
                n_epochs=n_epochs,
                lora=lora,
            )

            return ToolResult(success=True, result=estimate)

        except Exception as e:
            logger.exception("Nursery estimate cost error")
            return ToolResult(success=False, error=f"Failed to estimate cost: {str(e)}")


class NurseryTrainTool(BaseTool):
    """Start a cloud fine-tuning job on a Nursery dataset."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_train",
            description="""Start a cloud fine-tuning job via Together.ai.

Uploads the dataset, creates a training job, and begins fine-tuning.
Progress is tracked automatically in the background.

Requires a Together.ai API key configured in Settings > API Keys.

Use to:
- Fine-tune a model on your training data
- Create custom tool-calling models
- Train apprentice models for agents""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "description": "ID of the dataset to train on",
                    },
                    "base_model": {
                        "type": "string",
                        "description": "Base model for fine-tuning (default: meta-llama/Llama-3.2-3B-Instruct)",
                        "default": "meta-llama/Llama-3.2-3B-Instruct",
                    },
                    "n_epochs": {
                        "type": "integer",
                        "description": "Number of training epochs (default: 3)",
                        "default": 3,
                    },
                    "learning_rate": {
                        "type": "number",
                        "description": "Learning rate (default: 0.00001)",
                        "default": 0.00001,
                    },
                    "lora": {
                        "type": "boolean",
                        "description": "Use LoRA training (default: true)",
                        "default": True,
                    },
                    "suffix": {
                        "type": "string",
                        "description": "Custom suffix for the output model name (optional)",
                    },
                },
                "required": ["dataset_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        dataset_id = params.get("dataset_id")
        base_model = params.get("base_model", "meta-llama/Llama-3.2-3B-Instruct")
        n_epochs = params.get("n_epochs", 3)
        learning_rate = params.get("learning_rate", 1e-5)
        lora = params.get("lora", True)
        suffix = params.get("suffix")

        try:
            import os
            from app.services.nursery import NurseryService
            from app.services.cloud_trainer import CloudTrainerService, auto_complete_training_job
            from app.models.nursery import NurseryTrainingJob
            from app.models.user import User
            from app.models.billing import Subscription
            from app.services.provider_access import resolve_provider_access
            from app.database import get_db_context
            from sqlalchemy import select, func
            from uuid import uuid4

            # 1. Validate dataset
            dataset = await NurseryService.get_dataset(dataset_id, str(context.user_id))
            if not dataset:
                return ToolResult(success=False, error="Dataset not found")

            # Single DB context for user lookup, concurrent check, and job save
            async with get_db_context() as db:
                # 2. Get Together access (BYOK or platform grant)
                result = await db.execute(
                    select(User).where(User.id == UUID(str(context.user_id)))
                )
                user = result.scalar_one_or_none()

                if not user:
                    return ToolResult(success=False, error="User not found")

                sub_result = await db.execute(
                    select(Subscription).where(Subscription.user_id == user.id)
                )
                subscription = sub_result.scalar_one_or_none()
                tier = subscription.tier if subscription else "free_trial"

                access = await resolve_provider_access(user, "together", tier, db)
                if not access["allowed"]:
                    return ToolResult(
                        success=False,
                        error="Together.ai access required. Configure a key in Settings or contact admin.",
                    )
                api_key = access["api_key"]
                if api_key is None:
                    api_key = os.getenv("TOGETHER_API_KEY")

                # 3. Check concurrent job limit
                running_count_result = await db.execute(
                    select(func.count(NurseryTrainingJob.id)).where(
                        NurseryTrainingJob.user_id == UUID(str(context.user_id)),
                        NurseryTrainingJob.status.in_(["pending", "running", "uploading"]),
                    )
                )
                running_count = running_count_result.scalar() or 0
                if running_count >= 3:
                    return ToolResult(
                        success=False,
                        error="Maximum 3 concurrent training jobs. Wait for a job to complete or cancel one.",
                    )

                # 4. Get cost estimate
                num_examples = dataset.get("num_examples", 0)
                estimate = CloudTrainerService.estimate_cost(
                    num_examples=num_examples,
                    base_model=base_model,
                    n_epochs=n_epochs,
                    lora=lora,
                )

                # 5. Upload dataset to Together
                storage_path = dataset.get("storage_path", "")
                file_id = await CloudTrainerService.upload_dataset(storage_path, api_key)

                # 6. Create training job on Together
                job_info = await CloudTrainerService.create_training_job(
                    file_id=file_id,
                    base_model=base_model,
                    api_key=api_key,
                    n_epochs=n_epochs,
                    learning_rate=learning_rate,
                    lora=lora,
                    suffix=suffix,
                )

                # 7. Save job to DB
                job_id = uuid4()
                job = NurseryTrainingJob(
                    id=job_id,
                    user_id=UUID(str(context.user_id)),
                    dataset_id=UUID(dataset_id),
                    provider="together",
                    provider_job_id=job_info.get("job_id"),
                    base_model=base_model,
                    output_name=job_info.get("output_name"),
                    status="running",
                    progress=0.0,
                    config={
                        "n_epochs": n_epochs,
                        "learning_rate": learning_rate,
                        "lora": lora,
                        "suffix": suffix,
                        "file_id": file_id,
                    },
                    cost_estimate=estimate.get("estimated_cost_usd"),
                    agent_id=context.agent_id,
                    started_at=datetime.utcnow(),
                )
                db.add(job)
                await db.commit()

            # 8. Fire background polling task
            asyncio.create_task(
                auto_complete_training_job(str(job_id), str(context.user_id))
            )

            return ToolResult(
                success=True,
                result={
                    "job_id": str(job_id),
                    "status": "running",
                    "estimated_cost": estimate.get("estimated_cost_usd"),
                    "base_model": base_model,
                    "message": f"Training job started on Together.ai. Fine-tuning {base_model} with {num_examples} examples for {n_epochs} epochs.",
                },
            )

        except Exception as e:
            logger.exception("Nursery train error")
            return ToolResult(success=False, error=f"Failed to start training: {str(e)}")


class NurseryJobStatusTool(BaseTool):
    """Check the status of a training job."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_job_status",
            description="""Check the status of a Training Forge job.

Returns job status, progress, cost, and output model info.
If no job_id is given, returns the latest job.

Use to:
- Monitor training progress
- Check if a job completed or failed
- Get the output model name after training""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Training job ID (optional - returns latest if omitted)",
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        job_id = params.get("job_id")

        try:
            from app.models.nursery import NurseryTrainingJob
            from app.database import get_db_context
            from sqlalchemy import select

            async with get_db_context() as db:
                if job_id:
                    result = await db.execute(
                        select(NurseryTrainingJob).where(
                            NurseryTrainingJob.id == UUID(job_id),
                            NurseryTrainingJob.user_id == UUID(str(context.user_id)),
                        )
                    )
                else:
                    result = await db.execute(
                        select(NurseryTrainingJob)
                        .where(NurseryTrainingJob.user_id == UUID(str(context.user_id)))
                        .order_by(NurseryTrainingJob.created_at.desc())
                        .limit(1)
                    )

                job = result.scalar_one_or_none()

            if not job:
                return ToolResult(
                    success=False,
                    error="No training job found" if job_id else "No training jobs yet",
                )

            return ToolResult(
                success=True,
                result={
                    "id": str(job.id),
                    "status": job.status,
                    "progress": job.progress,
                    "base_model": job.base_model,
                    "provider": job.provider,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "cost_estimate": job.cost_estimate,
                    "error_message": job.error_message,
                    "output_name": job.output_name,
                },
            )

        except Exception as e:
            logger.exception("Nursery job status error")
            return ToolResult(success=False, error=f"Failed to get job status: {str(e)}")


class NurseryListJobsTool(BaseTool):
    """List training jobs."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_list_jobs",
            description="""List your Training Forge jobs.

Shows all training jobs with status, model, progress, and timestamps.
Optionally filter by status (pending, running, completed, failed).

Use to:
- See all training history
- Find completed models
- Check for running or failed jobs""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter by status: pending, running, completed, failed (optional)",
                        "enum": ["pending", "running", "completed", "failed"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 10)",
                        "default": 10,
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        status_filter = params.get("status_filter")
        limit = min(params.get("limit", 10), 50)

        try:
            from app.models.nursery import NurseryTrainingJob, NurseryDataset
            from app.database import get_db_context
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            async with get_db_context() as db:
                query = (
                    select(NurseryTrainingJob)
                    .options(selectinload(NurseryTrainingJob.dataset))
                    .where(NurseryTrainingJob.user_id == UUID(str(context.user_id)))
                )

                if status_filter:
                    query = query.where(NurseryTrainingJob.status == status_filter)

                query = query.order_by(NurseryTrainingJob.created_at.desc()).limit(limit)

                result = await db.execute(query)
                jobs = result.scalars().all()

            return ToolResult(
                success=True,
                result={
                    "count": len(jobs),
                    "jobs": [
                        {
                            "id": str(j.id),
                            "dataset_name": j.dataset.name if j.dataset else "unknown",
                            "base_model": j.base_model,
                            "status": j.status,
                            "progress": j.progress,
                            "created_at": j.created_at.isoformat() if j.created_at else None,
                        }
                        for j in jobs
                    ],
                },
            )

        except Exception as e:
            logger.exception("Nursery list jobs error")
            return ToolResult(success=False, error=f"Failed to list jobs: {str(e)}")


class NurseryListModelsTool(BaseTool):
    """List trained models in the Nursery's Model Cradle."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_list_models",
            description="""List your trained models in the Nursery's Model Cradle.

Shows model name, base model, type, capabilities, Village registration status,
and performance metrics.

Use to:
- See trained models
- Check which models are registered in the Village
- Find model IDs for registration or deletion""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default: 20)", "default": 20},
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")
        try:
            from app.database import get_db_context
            from app.models.nursery import NurseryModelRecord
            from sqlalchemy import select

            limit = min(params.get("limit", 20), 50)
            async with get_db_context() as db:
                result = await db.execute(
                    select(NurseryModelRecord)
                    .where(NurseryModelRecord.user_id == UUID(str(context.user_id)))
                    .order_by(NurseryModelRecord.created_at.desc())
                    .limit(limit)
                )
                models = result.scalars().all()

            return ToolResult(success=True, result={
                "count": len(models),
                "models": [
                    {
                        "id": str(m.id),
                        "name": m.name,
                        "base_model": m.base_model,
                        "model_type": m.model_type,
                        "capabilities": m.capabilities or [],
                        "village_posted": m.village_posted,
                        "performance": m.performance,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in models
                ],
            })
        except Exception as e:
            logger.exception("Nursery list models error")
            return ToolResult(success=False, error=f"Failed to list models: {str(e)}")


class NurseryRegisterModelTool(BaseTool):
    """Register a trained model in the Village for sharing."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_register_model",
            description="""Register a trained model in the Village for sharing.

Posts model information to Village memory so all agents across sessions can
discover and reference it. Sets the model's village_posted flag.

Use to:
- Share a trained model with the Village
- Make model capabilities discoverable
- Contribute to Village knowledge base""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "model_id": {"type": "string", "description": "ID of the model to register"},
                },
                "required": ["model_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")
        try:
            from app.database import get_db_context
            from app.models.nursery import NurseryModelRecord
            from app.services.neural_memory import NeuralMemoryService
            from sqlalchemy import select

            model_id = params.get("model_id")
            if not model_id:
                return ToolResult(success=False, error="model_id is required")

            async with get_db_context() as db:
                result = await db.execute(
                    select(NurseryModelRecord).where(
                        NurseryModelRecord.id == UUID(model_id),
                        NurseryModelRecord.user_id == UUID(str(context.user_id)),
                    )
                )
                model = result.scalar_one_or_none()
                if not model:
                    return ToolResult(success=False, error="Model not found")
                if model.village_posted:
                    return ToolResult(success=True, result={"message": "Model already registered in the Village.", "already_posted": True})

                model.village_posted = True
                neural = NeuralMemoryService(db)
                capabilities_str = ", ".join(model.capabilities or []) or "general"
                memory_content = (
                    f"Nursery model registered: {model.name}\n"
                    f"Base: {model.base_model}\n"
                    f"Type: {model.model_type}\n"
                    f"Capabilities: {capabilities_str}"
                )
                await neural.store_message(
                    user_id=UUID(str(context.user_id)),
                    content=memory_content,
                    agent_id=model.agent_id or "NURSERY",
                    role="assistant",
                    visibility="village",
                    collection="nursery",
                )
                await db.commit()

            return ToolResult(success=True, result={
                "model_id": model_id,
                "name": model.name,
                "message": f"Model '{model.name}' registered in the Village.",
            })
        except Exception as e:
            logger.exception("Nursery register model error")
            return ToolResult(success=False, error=f"Failed to register model: {str(e)}")


class NurseryDiscoverModelsTool(BaseTool):
    """Search the Village for shared trained models."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_discover_models",
            description="""Search the Village for shared trained models.

Searches Village memory for models registered by you or shared across sessions.
Uses semantic search when query provided, recency-based when not.

Use to:
- Find available trained models
- Discover model capabilities
- Browse the Village model catalog""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (optional -- returns recent if omitted)"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")
        try:
            from app.database import get_db_context
            from app.services.neural_memory import NeuralMemoryService

            query = params.get("query")
            limit = min(params.get("limit", 10), 50)

            async with get_db_context() as db:
                neural = NeuralMemoryService(db)
                memories = await neural.get_village_memories(
                    user_id=UUID(str(context.user_id)),
                    topic=query,
                    limit=limit,
                    collection="nursery",
                )

            return ToolResult(success=True, result={
                "count": len(memories),
                "query": query,
                "models": memories,
            })
        except Exception as e:
            logger.exception("Nursery discover models error")
            return ToolResult(success=False, error=f"Failed to discover models: {str(e)}")


class NurseryCreateApprenticeTool(BaseTool):
    """Create an apprentice under a master agent."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_create_apprentice",
            description="""Create an apprentice model under a master agent.

An apprentice is a trainable model raised by one of the four alchemists
(AZOTH, ELYSIAN, VAJRA, KETHER). Optionally auto-generates a training
dataset from the specialization tools.

Use to:
- Create a new apprentice for an agent
- Optionally auto-generate training data
- Begin the apprentice training pipeline""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "master_agent": {
                        "type": "string",
                        "enum": ["AZOTH", "ELYSIAN", "VAJRA", "KETHER"],
                        "description": "Master agent raising this apprentice",
                    },
                    "apprentice_name": {
                        "type": "string",
                        "description": "Name for the apprentice",
                    },
                    "specialization": {
                        "type": "string",
                        "description": "Comma-separated tool names for specialization (e.g., 'calculate,web_search')",
                    },
                    "auto_generate": {
                        "type": "boolean",
                        "description": "Auto-generate a training dataset from specialization tools (default: false)",
                        "default": False,
                    },
                    "num_examples": {
                        "type": "integer",
                        "description": "Number of training examples to generate (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["master_agent", "apprentice_name"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        master_agent = params.get("master_agent", "")
        apprentice_name = params.get("apprentice_name", "")
        specialization = params.get("specialization")
        auto_generate = params.get("auto_generate", False)
        num_examples = min(params.get("num_examples", 50), 500)

        valid_masters = {"AZOTH", "ELYSIAN", "VAJRA", "KETHER"}
        if master_agent not in valid_masters:
            return ToolResult(success=False, error=f"Invalid master_agent. Must be one of: {', '.join(sorted(valid_masters))}")

        if not apprentice_name or len(apprentice_name.strip()) < 2:
            return ToolResult(success=False, error="Apprentice name must be at least 2 characters")

        try:
            from app.database import get_db_context
            from app.models.nursery import NurseryApprentice
            from uuid import uuid4

            apprentice_id = uuid4()
            dataset_id = None
            final_num_examples = 0

            # Optional: auto-generate training dataset
            if auto_generate and specialization:
                from app.services.nursery import NurseryService
                from app.tools import registry as tool_registry

                tool_names = [t.strip() for t in specialization.split(",") if t.strip()]

                # Validate tool names
                all_tools = tool_registry.get_all_tools()
                valid_tool_names = {t.schema.name for t in all_tools}
                tool_names = [t for t in tool_names if t in valid_tool_names]

                if not tool_names:
                    fallback = ["calculate", "web_search", "vault_list", "cortex_recall"]
                    tool_names = [t for t in fallback if t in valid_tool_names]

                if tool_names:
                    ds_name = f"apprentice_{apprentice_name.strip().lower().replace(' ', '_')}_{master_agent.lower()}"
                    result = await NurseryService.generate_synthetic_data(
                        tool_names=tool_names,
                        num_examples=num_examples,
                        variation_level="medium",
                        user_id=str(context.user_id),
                        agent_id=master_agent,
                        dataset_name=ds_name,
                    )
                    if result.get("success"):
                        dataset_id = UUID(result["dataset_id"])
                        final_num_examples = result["num_examples"]

            async with get_db_context() as db:
                apprentice = NurseryApprentice(
                    id=apprentice_id,
                    user_id=UUID(str(context.user_id)),
                    master_agent=master_agent,
                    apprentice_name=apprentice_name.strip(),
                    specialization=specialization.strip() if specialization else None,
                    dataset_id=dataset_id,
                    num_examples=final_num_examples,
                    status="dataset_ready",
                )
                db.add(apprentice)
                await db.commit()

            message = f"Apprentice '{apprentice_name.strip()}' created under {master_agent}."
            if dataset_id:
                message += f" Dataset generated with {final_num_examples} examples."

            return ToolResult(
                success=True,
                result={
                    "apprentice_id": str(apprentice_id),
                    "master_agent": master_agent,
                    "apprentice_name": apprentice_name.strip(),
                    "specialization": specialization,
                    "dataset_id": str(dataset_id) if dataset_id else None,
                    "num_examples": final_num_examples,
                    "message": message,
                },
            )

        except Exception as e:
            logger.exception("Nursery create apprentice error")
            return ToolResult(success=False, error=f"Failed to create apprentice: {str(e)}")


class NurseryListApprenticesTool(BaseTool):
    """List apprentices in the Nursery."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_list_apprentices",
            description="""List your apprentices in the Nursery.

Shows apprentice name, master agent, specialization, status,
linked dataset and model info.

Use to:
- See all apprentices and their training status
- Find apprentice IDs for training or deletion
- Check which agents have apprentices""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["dataset_ready", "training", "trained", "failed"],
                        "description": "Filter by status (optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        status_filter = params.get("status_filter")
        limit = min(params.get("limit", 20), 50)

        try:
            from app.database import get_db_context
            from app.models.nursery import NurseryApprentice
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            async with get_db_context() as db:
                query = (
                    select(NurseryApprentice)
                    .options(
                        selectinload(NurseryApprentice.dataset),
                        selectinload(NurseryApprentice.model),
                    )
                    .where(NurseryApprentice.user_id == UUID(str(context.user_id)))
                )

                if status_filter:
                    query = query.where(NurseryApprentice.status == status_filter)

                query = query.order_by(NurseryApprentice.created_at.desc()).limit(limit)

                result = await db.execute(query)
                apprentices = result.scalars().all()

            return ToolResult(
                success=True,
                result={
                    "count": len(apprentices),
                    "apprentices": [
                        {
                            "id": str(a.id),
                            "apprentice_name": a.apprentice_name,
                            "master_agent": a.master_agent,
                            "specialization": a.specialization,
                            "status": a.status,
                            "num_examples": a.num_examples,
                            "dataset_name": a.dataset.name if a.dataset else None,
                            "model_name": a.model.name if a.model else None,
                        }
                        for a in apprentices
                    ],
                },
            )

        except Exception as e:
            logger.exception("Nursery list apprentices error")
            return ToolResult(success=False, error=f"Failed to list apprentices: {str(e)}")


class NurseryAutoTrainTool(BaseTool):
    """Auto-train an apprentice with cost guard."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="nursery_auto_train",
            description="""Auto-train an apprentice model end-to-end with a cost guard.

Resolves the dataset (from the apprentice record or a direct dataset_id),
validates it, estimates cost, checks against max_cost budget, uploads to
Together.ai, starts the training job, links the apprentice, and fires
background polling.

Use to:
- Train an apprentice in one step
- Safely train with a cost budget
- Automate the full training pipeline""",
            category=ToolCategory.NURSERY,
            input_schema={
                "type": "object",
                "properties": {
                    "apprentice_id": {
                        "type": "string",
                        "description": "Apprentice ID to train",
                    },
                    "dataset_id": {
                        "type": "string",
                        "description": "Dataset ID (optional -- uses apprentice's dataset if omitted)",
                    },
                    "base_model": {
                        "type": "string",
                        "description": "Base model for fine-tuning (default: meta-llama/Llama-3.2-3B-Instruct)",
                        "default": "meta-llama/Llama-3.2-3B-Instruct",
                    },
                    "n_epochs": {
                        "type": "integer",
                        "description": "Number of training epochs (default: 3)",
                        "default": 3,
                    },
                    "learning_rate": {
                        "type": "number",
                        "description": "Learning rate (default: 0.00001)",
                        "default": 0.00001,
                    },
                    "lora": {
                        "type": "boolean",
                        "description": "Use LoRA training (default: true)",
                        "default": True,
                    },
                    "max_cost": {
                        "type": "number",
                        "description": "Maximum allowed cost in USD (default: 5.0). Aborts if estimate exceeds this.",
                        "default": 5.0,
                    },
                },
                "required": ["apprentice_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        apprentice_id = params.get("apprentice_id")
        dataset_id = params.get("dataset_id")
        base_model = params.get("base_model", "meta-llama/Llama-3.2-3B-Instruct")
        n_epochs = params.get("n_epochs", 3)
        learning_rate = params.get("learning_rate", 1e-5)
        lora = params.get("lora", True)
        max_cost = params.get("max_cost", 5.0)

        if not apprentice_id:
            return ToolResult(success=False, error="apprentice_id is required")

        try:
            import os
            from app.database import get_db_context
            from app.models.nursery import NurseryApprentice, NurseryTrainingJob
            from app.models.user import User
            from app.models.billing import Subscription
            from app.services.nursery import NurseryService
            from app.services.cloud_trainer import CloudTrainerService, auto_complete_training_job
            from app.services.provider_access import resolve_provider_access
            from sqlalchemy import select, func
            from uuid import uuid4

            # 1. Resolve apprentice, user, and check concurrent jobs in one DB context
            async with get_db_context() as db:
                ap_result = await db.execute(
                    select(NurseryApprentice).where(
                        NurseryApprentice.id == UUID(apprentice_id),
                        NurseryApprentice.user_id == UUID(str(context.user_id)),
                    )
                )
                apprentice = ap_result.scalar_one_or_none()

                if not apprentice:
                    return ToolResult(success=False, error="Apprentice not found")

                user_result = await db.execute(
                    select(User).where(User.id == UUID(str(context.user_id)))
                )
                user = user_result.scalar_one_or_none()

                if not user:
                    return ToolResult(success=False, error="User not found")

                # Check concurrent job limit
                running_count_result = await db.execute(
                    select(func.count(NurseryTrainingJob.id)).where(
                        NurseryTrainingJob.user_id == UUID(str(context.user_id)),
                        NurseryTrainingJob.status.in_(["pending", "running", "uploading"]),
                    )
                )
                running_count = running_count_result.scalar() or 0
                if running_count >= 3:
                    return ToolResult(
                        success=False,
                        error="Maximum 3 concurrent training jobs. Wait for a job to complete or cancel one.",
                    )

            # Resolve dataset: prefer explicit param, fall back to apprentice's dataset
            resolved_dataset_id = dataset_id or (str(apprentice.dataset_id) if apprentice.dataset_id else None)
            if not resolved_dataset_id:
                return ToolResult(success=False, error="No dataset available. Provide dataset_id or create an apprentice with auto_generate.")

            # 2. Validate dataset
            dataset = await NurseryService.get_dataset(resolved_dataset_id, str(context.user_id))
            if not dataset:
                return ToolResult(success=False, error="Dataset not found")

            num_examples = dataset.get("num_examples", 0)

            # 3. Get Together access (BYOK or platform grant)
            async with get_db_context() as db:
                sub_result = await db.execute(
                    select(Subscription).where(Subscription.user_id == user.id)
                )
                subscription = sub_result.scalar_one_or_none()
                tier = subscription.tier if subscription else "free_trial"

                access = await resolve_provider_access(user, "together", tier, db)
            if not access["allowed"]:
                return ToolResult(
                    success=False,
                    error="Together.ai access required. Configure a key in Settings or contact admin.",
                )
            api_key = access["api_key"]
            if api_key is None:
                api_key = os.getenv("TOGETHER_API_KEY")

            # 4. Estimate cost
            estimate = CloudTrainerService.estimate_cost(
                num_examples=num_examples,
                base_model=base_model,
                n_epochs=n_epochs,
                lora=lora,
            )

            # 5. COST GUARD
            estimated_cost = estimate.get("estimated_cost_usd", 0)
            if estimated_cost > max_cost:
                return ToolResult(
                    success=False,
                    error=f"Estimated cost ${estimated_cost:.2f} exceeds max_cost ${max_cost:.2f}. Increase max_cost or reduce dataset/epochs.",
                )

            # 6. Upload dataset to Together
            storage_path = dataset.get("storage_path", "")
            file_id = await CloudTrainerService.upload_dataset(storage_path, api_key)

            # 7. Create training job on Together
            job_info = await CloudTrainerService.create_training_job(
                file_id=file_id,
                base_model=base_model,
                api_key=api_key,
                n_epochs=n_epochs,
                learning_rate=learning_rate,
                lora=lora,
                suffix=f"apprentice-{apprentice.apprentice_name.lower().replace(' ', '-')}",
            )

            # 8. Save job to DB and update apprentice status
            job_id = uuid4()
            async with get_db_context() as db:
                job = NurseryTrainingJob(
                    id=job_id,
                    user_id=UUID(str(context.user_id)),
                    dataset_id=UUID(resolved_dataset_id),
                    provider="together",
                    provider_job_id=job_info.get("job_id"),
                    base_model=base_model,
                    output_name=job_info.get("output_name"),
                    status="running",
                    progress=0.0,
                    config={
                        "n_epochs": n_epochs,
                        "learning_rate": learning_rate,
                        "lora": lora,
                        "file_id": file_id,
                        "apprentice_id": apprentice_id,
                    },
                    cost_estimate=estimated_cost,
                    agent_id=context.agent_id,
                    started_at=datetime.utcnow(),
                )
                db.add(job)

                # Update apprentice status to training
                ap_result = await db.execute(
                    select(NurseryApprentice).where(
                        NurseryApprentice.id == UUID(apprentice_id),
                    )
                )
                ap = ap_result.scalar_one_or_none()
                if ap:
                    ap.status = "training"

                await db.commit()

            # 9. Fire background polling task
            asyncio.create_task(
                auto_complete_training_job(str(job_id), str(context.user_id))
            )

            return ToolResult(
                success=True,
                result={
                    "job_id": str(job_id),
                    "apprentice_id": apprentice_id,
                    "apprentice_name": apprentice.apprentice_name,
                    "status": "running",
                    "estimated_cost": estimated_cost,
                    "max_cost": max_cost,
                    "base_model": base_model,
                    "num_examples": num_examples,
                    "message": f"Auto-training apprentice '{apprentice.apprentice_name}' on {base_model} with {num_examples} examples. Estimated cost: ${estimated_cost:.2f}.",
                },
            )

        except Exception as e:
            logger.exception("Nursery auto-train error")
            return ToolResult(success=False, error=f"Failed to auto-train: {str(e)}")


# Register tools
registry.register(NurseryGenerateDataTool())
registry.register(NurseryExtractDataTool())
registry.register(NurseryListDatasetsTool())
registry.register(NurseryEstimateCostTool())
registry.register(NurseryTrainTool())
registry.register(NurseryJobStatusTool())
registry.register(NurseryListJobsTool())
registry.register(NurseryListModelsTool())
registry.register(NurseryRegisterModelTool())
registry.register(NurseryDiscoverModelsTool())
registry.register(NurseryCreateApprenticeTool())
registry.register(NurseryListApprenticesTool())
registry.register(NurseryAutoTrainTool())
