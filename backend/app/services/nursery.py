"""
NurseryService - The Growth Chamber

Data generation and dataset management for model training.
"From data, new minds are born."
"""

import json
import hashlib
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, delete

from app.config import get_settings

logger = logging.getLogger(__name__)


class NurseryService:
    """Service for nursery dataset operations."""

    @staticmethod
    def _get_datasets_path(user_id: str) -> Path:
        """Get user's nursery datasets directory, creating if needed."""
        settings = get_settings()
        path = Path(settings.vault_path) / "users" / str(user_id) / "nursery" / "datasets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    async def generate_synthetic_data(
        tool_names: list[str],
        num_examples: int,
        variation_level: str,
        user_id: str,
        agent_id: Optional[str] = None,
        dataset_name: Optional[str] = None,
    ) -> dict:
        """
        Generate synthetic training data for specified tools.

        Uses the tool registry to get schemas, then generates varied
        user queries + tool call pairs in ChatML JSONL format.

        Returns dict with dataset info.
        """
        from app.models.nursery import NurseryDataset
        from app.database import async_session
        from app.tools import registry

        # Get tool schemas from registry
        all_tools = registry.get_all_tools()
        tool_map = {t.schema.name: t.schema for t in all_tools}

        matched_tools = []
        for tn in tool_names:
            if tn in tool_map:
                matched_tools.append(tool_map[tn])

        if not matched_tools:
            return {"success": False, "error": f"No matching tools found. Available: {list(tool_map.keys())[:20]}"}

        # Generate examples
        examples = _generate_examples(matched_tools, num_examples, variation_level)

        if not examples:
            return {"success": False, "error": "Failed to generate any examples"}

        # Create dataset record
        dataset_id = uuid4()
        if not dataset_name:
            tool_str = "_".join(tool_names[:3])
            dataset_name = f"synthetic_{tool_str}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Write JSONL
        datasets_path = NurseryService._get_datasets_path(user_id)
        file_path = datasets_path / f"{dataset_id}.jsonl"

        size_bytes = 0
        with open(file_path, "w") as f:
            for ex in examples:
                line = json.dumps(ex, ensure_ascii=False) + "\n"
                f.write(line)
                size_bytes += len(line.encode("utf-8"))

        storage_path = f"vault/users/{user_id}/nursery/datasets/{dataset_id}.jsonl"

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            dataset = NurseryDataset(
                id=dataset_id,
                user_id=user_uuid,
                name=dataset_name,
                source="synthetic",
                tool_names=tool_names,
                num_examples=len(examples),
                size_bytes=size_bytes,
                storage_path=storage_path,
                agent_id=agent_id,
            )
            db.add(dataset)
            await db.commit()

        # Post Village event
        try:
            from app.services.village_events import get_village_broadcaster
            broadcaster = get_village_broadcaster()
            await broadcaster.broadcast({
                "type": "nursery_event",
                "event": "dataset_created",
                "agent_id": agent_id or "NURSERY_KEEPER",
                "data": {
                    "dataset_name": dataset_name,
                    "num_examples": len(examples),
                    "tools": tool_names,
                    "source": "synthetic",
                },
            })
        except Exception:
            logger.debug("Village broadcast skipped")

        return {
            "success": True,
            "dataset_id": str(dataset_id),
            "name": dataset_name,
            "num_examples": len(examples),
            "size_bytes": size_bytes,
            "tools": tool_names,
            "storage_path": storage_path,
        }

    @staticmethod
    async def extract_conversation_data(
        user_id: str,
        tools_filter: Optional[list[str]] = None,
        min_examples: int = 10,
        agent_id: Optional[str] = None,
        dataset_name: Optional[str] = None,
    ) -> dict:
        """
        Extract training data from user's conversation history.

        Finds messages where tools were called, pairs them with the
        preceding user message to create training examples.
        """
        from app.models.nursery import NurseryDataset
        from app.models.conversation import Message, Conversation
        from app.database import async_session

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

            # Get user's conversations
            conv_result = await db.execute(
                select(Conversation.id).where(Conversation.user_id == user_uuid)
            )
            conv_ids = [row[0] for row in conv_result.all()]

            if not conv_ids:
                return {"success": False, "error": "No conversations found"}

            # Get messages with tool calls
            msg_result = await db.execute(
                select(Message).where(
                    Message.conversation_id.in_(conv_ids),
                    Message.tool_calls.isnot(None),
                    Message.role == "assistant",
                ).order_by(Message.created_at)
            )
            tool_messages = msg_result.scalars().all()

            if not tool_messages:
                return {"success": False, "error": "No tool calls found in conversation history"}

            # Get ALL messages for context lookup (the user message before each tool call)
            all_msg_result = await db.execute(
                select(Message).where(
                    Message.conversation_id.in_(conv_ids)
                ).order_by(Message.conversation_id, Message.created_at)
            )
            all_messages = all_msg_result.scalars().all()

            # Group messages by conversation for context lookup
            conv_messages = {}
            for msg in all_messages:
                cid = str(msg.conversation_id)
                if cid not in conv_messages:
                    conv_messages[cid] = []
                conv_messages[cid].append(msg)

            # Extract examples
            examples = []
            seen_hashes = set()
            tool_counts = {}

            for tool_msg in tool_messages:
                if not tool_msg.tool_calls:
                    continue

                # Parse tool_calls (could be list or dict)
                calls = tool_msg.tool_calls if isinstance(tool_msg.tool_calls, list) else [tool_msg.tool_calls]

                for call in calls:
                    tool_name = call.get("name", "")
                    tool_args = call.get("input", {})

                    if not tool_name:
                        continue

                    # Apply filter
                    if tools_filter and tool_name not in tools_filter:
                        continue

                    # Find preceding user message
                    cid = str(tool_msg.conversation_id)
                    msgs_in_conv = conv_messages.get(cid, [])
                    user_content = ""
                    for i, m in enumerate(msgs_in_conv):
                        if str(m.id) == str(tool_msg.id) and i > 0:
                            # Walk back to find user message
                            for j in range(i - 1, -1, -1):
                                if msgs_in_conv[j].role == "user":
                                    user_content = msgs_in_conv[j].content
                                    break
                            break

                    if not user_content or len(user_content) < 5:
                        continue

                    # Deduplicate
                    hash_key = hashlib.md5(
                        f"{user_content}:{tool_name}:{json.dumps(tool_args, sort_keys=True)}".encode()
                    ).hexdigest()
                    if hash_key in seen_hashes:
                        continue
                    seen_hashes.add(hash_key)

                    # Build ChatML training example
                    example = {
                        "messages": [
                            {"role": "system", "content": "You are an AI assistant with access to tools. Call the appropriate tool when the user's request matches a tool's capability."},
                            {"role": "user", "content": user_content},
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_args),
                                    }
                                }]
                            }
                        ]
                    }
                    examples.append(example)
                    tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

            if len(examples) < min_examples:
                return {
                    "success": False,
                    "error": f"Only found {len(examples)} examples (minimum: {min_examples}). Try lowering min_examples or removing tool filters.",
                    "found": len(examples),
                }

            # Write JSONL
            dataset_id = uuid4()
            if not dataset_name:
                dataset_name = f"extracted_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            datasets_path = NurseryService._get_datasets_path(user_id)
            file_path = datasets_path / f"{dataset_id}.jsonl"

            size_bytes = 0
            with open(file_path, "w") as f:
                for ex in examples:
                    line = json.dumps(ex, ensure_ascii=False) + "\n"
                    f.write(line)
                    size_bytes += len(line.encode("utf-8"))

            # Create DB record
            extracted_tools = list(tool_counts.keys())
            dataset = NurseryDataset(
                id=dataset_id,
                user_id=user_uuid,
                name=dataset_name,
                source="extracted",
                tool_names=extracted_tools,
                num_examples=len(examples),
                size_bytes=size_bytes,
                storage_path=f"vault/users/{user_id}/nursery/datasets/{dataset_id}.jsonl",
                agent_id=agent_id,
            )
            db.add(dataset)
            await db.commit()

        # Village event
        try:
            from app.services.village_events import get_village_broadcaster
            broadcaster = get_village_broadcaster()
            await broadcaster.broadcast({
                "type": "nursery_event",
                "event": "dataset_extracted",
                "agent_id": agent_id or "NURSERY_KEEPER",
                "data": {
                    "dataset_name": dataset_name,
                    "num_examples": len(examples),
                    "tools": extracted_tools,
                    "source": "extracted",
                },
            })
        except Exception:
            logger.debug("Village broadcast skipped")

        return {
            "success": True,
            "dataset_id": str(dataset_id),
            "name": dataset_name,
            "num_examples": len(examples),
            "size_bytes": size_bytes,
            "tools_extracted": tool_counts,
            "storage_path": f"vault/users/{user_id}/nursery/datasets/{dataset_id}.jsonl",
        }

    @staticmethod
    async def list_datasets(user_id: str) -> list[dict]:
        """List all datasets for a user."""
        from app.models.nursery import NurseryDataset
        from app.database import async_session

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            result = await db.execute(
                select(NurseryDataset)
                .where(NurseryDataset.user_id == user_uuid)
                .order_by(NurseryDataset.created_at.desc())
            )
            datasets = result.scalars().all()

            return [
                {
                    "id": str(ds.id),
                    "name": ds.name,
                    "source": ds.source,
                    "tool_names": ds.tool_names or [],
                    "num_examples": ds.num_examples,
                    "size_bytes": ds.size_bytes,
                    "size_kb": round(ds.size_bytes / 1024, 1) if ds.size_bytes else 0,
                    "agent_id": ds.agent_id,
                    "created_at": ds.created_at.isoformat() if ds.created_at else None,
                }
                for ds in datasets
            ]

    @staticmethod
    async def get_dataset(dataset_id: str, user_id: str) -> Optional[dict]:
        """Get a single dataset with preview."""
        from app.models.nursery import NurseryDataset
        from app.database import async_session

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            ds_uuid = UUID(dataset_id)

            result = await db.execute(
                select(NurseryDataset).where(
                    NurseryDataset.id == ds_uuid,
                    NurseryDataset.user_id == user_uuid,
                )
            )
            ds = result.scalar_one_or_none()
            if not ds:
                return None

            # Read preview (first 5 lines)
            preview = []
            settings = get_settings()
            file_path = Path(settings.vault_path) / "users" / str(user_id) / "nursery" / "datasets" / f"{dataset_id}.jsonl"
            if file_path.exists():
                with open(file_path) as f:
                    for i, line in enumerate(f):
                        if i >= 5:
                            break
                        try:
                            preview.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            pass

            return {
                "id": str(ds.id),
                "name": ds.name,
                "source": ds.source,
                "tool_names": ds.tool_names or [],
                "num_examples": ds.num_examples,
                "size_bytes": ds.size_bytes,
                "size_kb": round(ds.size_bytes / 1024, 1) if ds.size_bytes else 0,
                "agent_id": ds.agent_id,
                "storage_path": ds.storage_path,
                "created_at": ds.created_at.isoformat() if ds.created_at else None,
                "preview": preview,
            }

    @staticmethod
    async def delete_dataset(dataset_id: str, user_id: str) -> bool:
        """Delete a dataset and its JSONL file."""
        from app.models.nursery import NurseryDataset
        from app.database import async_session

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            ds_uuid = UUID(dataset_id)

            result = await db.execute(
                select(NurseryDataset).where(
                    NurseryDataset.id == ds_uuid,
                    NurseryDataset.user_id == user_uuid,
                )
            )
            ds = result.scalar_one_or_none()
            if not ds:
                return False

            # Delete file
            settings = get_settings()
            file_path = Path(settings.vault_path) / "users" / str(user_id) / "nursery" / "datasets" / f"{dataset_id}.jsonl"
            if file_path.exists():
                file_path.unlink()

            await db.delete(ds)
            await db.commit()
            return True

    @staticmethod
    async def get_stats(user_id: str) -> dict:
        """Get nursery statistics for a user."""
        from app.models.nursery import NurseryDataset, NurseryTrainingJob, NurseryModelRecord, NurseryApprentice
        from app.database import async_session

        async with async_session() as db:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

            # Count datasets
            ds_count = await db.scalar(
                select(func.count()).select_from(NurseryDataset).where(NurseryDataset.user_id == user_uuid)
            )
            ds_examples = await db.scalar(
                select(func.coalesce(func.sum(NurseryDataset.num_examples), 0))
                .where(NurseryDataset.user_id == user_uuid)
            )

            # Count jobs
            job_count = await db.scalar(
                select(func.count()).select_from(NurseryTrainingJob).where(NurseryTrainingJob.user_id == user_uuid)
            )
            jobs_completed = await db.scalar(
                select(func.count()).select_from(NurseryTrainingJob).where(
                    NurseryTrainingJob.user_id == user_uuid,
                    NurseryTrainingJob.status == "completed",
                )
            )

            # Count models
            model_count = await db.scalar(
                select(func.count()).select_from(NurseryModelRecord).where(NurseryModelRecord.user_id == user_uuid)
            )

            # Count apprentices
            apprentice_count = await db.scalar(
                select(func.count()).select_from(NurseryApprentice).where(NurseryApprentice.user_id == user_uuid)
            )

            return {
                "datasets": ds_count or 0,
                "total_examples": ds_examples or 0,
                "training_jobs": job_count or 0,
                "jobs_completed": jobs_completed or 0,
                "models": model_count or 0,
                "apprentices": apprentice_count or 0,
            }


# ═══════════════════════════════════════════════════════════════════════
# SYNTHETIC DATA GENERATION (rule-based, no LLM needed)
# ═══════════════════════════════════════════════════════════════════════

# Query templates for variation
_QUERY_TEMPLATES = {
    "low": [
        "{action}",
    ],
    "medium": [
        "{action}",
        "Can you {action}?",
        "Please {action}",
        "I need to {action}",
        "{action} for me",
    ],
    "high": [
        "{action}",
        "Can you {action}?",
        "Please {action}",
        "I need to {action}",
        "{action} for me",
        "Hey, could you {action}?",
        "I'd like to {action}",
        "Help me {action}",
        "Would you mind {action}?",
        "Go ahead and {action}",
    ],
}

# Example actions per common tool pattern
_TOOL_ACTIONS = {
    "calculator": [
        ("calculate {a} {op} {b}", {"a": "int", "b": "int", "op": "choice:add,subtract,multiply,divide"}),
        ("what is {a} plus {b}", {"operation": "const:add", "a": "int", "b": "int"}),
        ("multiply {a} by {b}", {"operation": "const:multiply", "a": "int", "b": "int"}),
        ("divide {a} by {b}", {"operation": "const:divide", "a": "int", "b": "int"}),
    ],
    "get_current_time": [
        ("what time is it", {}),
        ("current time", {}),
        ("what's the time now", {}),
    ],
    "vault_list": [
        ("show my files", {}),
        ("list files in my vault", {}),
        ("what files do I have", {}),
    ],
    "vault_read": [
        ("read the file {filename}", {"path": "str"}),
        ("show me {filename}", {"path": "str"}),
        ("open {filename}", {"path": "str"}),
    ],
    "web_search": [
        ("search for {query}", {"query": "str"}),
        ("find information about {query}", {"query": "str"}),
        ("look up {query}", {"query": "str"}),
    ],
    "cortex_recall": [
        ("what do you remember about {topic}", {"query": "str"}),
        ("search memory for {topic}", {"query": "str"}),
        ("recall {topic}", {"query": "str"}),
    ],
}

# Generic fallback for unknown tools
_GENERIC_ACTIONS = [
    ("use {tool_name}", {}),
    ("run {tool_name}", {}),
    ("execute {tool_name} tool", {}),
    ("call {tool_name}", {}),
]


def _generate_param_value(param_type: str) -> any:
    """Generate a random parameter value based on type hint."""
    if param_type == "int":
        return random.randint(1, 100)
    elif param_type == "str":
        words = ["report", "document", "notes", "data", "analysis", "summary", "project", "todo"]
        return random.choice(words)
    elif param_type.startswith("const:"):
        return param_type.split(":", 1)[1]
    elif param_type.startswith("choice:"):
        choices = param_type.split(":", 1)[1].split(",")
        return random.choice(choices)
    return "example"


def _generate_examples(
    tool_schemas: list,
    num_examples: int,
    variation_level: str = "medium",
) -> list[dict]:
    """Generate synthetic training examples for tools.

    Returns list of ChatML-format dicts ready for JSONL.
    """
    templates = _QUERY_TEMPLATES.get(variation_level, _QUERY_TEMPLATES["medium"])
    examples = []

    per_tool = max(1, num_examples // len(tool_schemas))

    for schema in tool_schemas:
        tool_name = schema.name
        tool_desc = schema.description
        input_schema = schema.input_schema

        # Get known actions or use generic
        known_actions = _TOOL_ACTIONS.get(tool_name, [])

        for i in range(per_tool):
            if known_actions:
                action_template, param_hints = random.choice(known_actions)
            else:
                action_template, param_hints = random.choice(_GENERIC_ACTIONS)
                action_template = action_template.replace("{tool_name}", tool_name)

            # Fill in template variables
            filled_action = action_template
            tool_args = {}

            # Generate arguments from schema properties
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            for prop_name, prop_def in properties.items():
                prop_type = prop_def.get("type", "string")

                # Check if we have a hint for this param
                if prop_name in param_hints:
                    val = _generate_param_value(param_hints[prop_name])
                elif prop_type == "string":
                    val = _generate_param_value("str")
                elif prop_type == "integer":
                    val = _generate_param_value("int")
                elif prop_type == "number":
                    val = round(random.uniform(0, 100), 2)
                elif prop_type == "boolean":
                    val = random.choice([True, False])
                else:
                    val = "example"

                # Only include required params + randomly include optional
                if prop_name in required or random.random() > 0.5:
                    tool_args[prop_name] = val

                # Try to fill template placeholders
                filled_action = filled_action.replace(f"{{{prop_name}}}", str(val))

            # Fill any remaining template vars
            for placeholder in ["{a}", "{b}", "{op}", "{query}", "{topic}", "{filename}"]:
                key = placeholder.strip("{}")
                if placeholder in filled_action:
                    if key in tool_args:
                        filled_action = filled_action.replace(placeholder, str(tool_args[key]))
                    else:
                        filled_action = filled_action.replace(placeholder, _generate_param_value("str"))

            # Apply query template variation
            query_template = random.choice(templates)
            user_query = query_template.replace("{action}", filled_action)

            # Build ChatML example
            example = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an AI assistant with access to tools. Call the appropriate tool when the user's request matches a tool's capability."
                    },
                    {
                        "role": "user",
                        "content": user_query
                    },
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args),
                            }
                        }]
                    }
                ]
            }
            examples.append(example)

    # Shuffle and trim to exact count
    random.shuffle(examples)
    return examples[:num_examples]
