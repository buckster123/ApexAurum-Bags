"""
Tier 5: Session Memory Tools - The Remembering Hands

Per-conversation scratchpad for multi-step reasoning.
"Hold context across steps within a conversation"

The scratch pad is stored in conversation metadata and
persists for the duration of the conversation.
"""

import logging
import json
from typing import Optional

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)

# Limits
MAX_SCRATCH_KEYS = 100
MAX_VALUE_SIZE = 10 * 1024  # 10KB per value
MAX_TOTAL_SIZE = 100 * 1024  # 100KB total


# In-memory scratch storage (per conversation)
# In production, this would be stored in conversation metadata
_scratch_storage: dict[str, dict] = {}


def _get_scratch(conversation_id: Optional[str]) -> dict:
    """Get scratch storage for a conversation."""
    if not conversation_id:
        conversation_id = "_anonymous"
    if conversation_id not in _scratch_storage:
        _scratch_storage[conversation_id] = {}
    return _scratch_storage[conversation_id]


def _estimate_size(data: dict) -> int:
    """Estimate size of scratch data in bytes."""
    return len(json.dumps(data))


# =============================================================================
# SCRATCH STORE
# =============================================================================

class ScratchStoreTool(BaseTool):
    """Store a value in the conversation scratchpad."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="scratch_store",
            description="""Store a key-value pair in the conversation scratchpad.

Use for:
- Saving intermediate results during multi-step tasks
- Remembering context within a conversation
- Storing data to reference later in the same chat

Data persists for the conversation duration only.
Max 100 keys, 10KB per value, 100KB total.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Unique key to identify this data",
                    },
                    "value": {
                        "description": "Value to store (string, number, object, or array)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of what this data is for",
                    },
                },
                "required": ["key", "value"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        key = params.get("key", "")
        value = params.get("value")
        description = params.get("description")

        if not key:
            return ToolResult(success=False, error="Key is required")

        if value is None:
            return ToolResult(success=False, error="Value is required")

        scratch = _get_scratch(context.conversation_id)

        # Check key limit
        if key not in scratch and len(scratch) >= MAX_SCRATCH_KEYS:
            return ToolResult(
                success=False,
                error=f"Maximum {MAX_SCRATCH_KEYS} keys reached. Delete some keys first.",
            )

        # Check value size
        value_json = json.dumps(value)
        if len(value_json) > MAX_VALUE_SIZE:
            return ToolResult(
                success=False,
                error=f"Value exceeds {MAX_VALUE_SIZE // 1024}KB limit",
            )

        # Check total size
        test_scratch = {**scratch, key: {"value": value}}
        if _estimate_size(test_scratch) > MAX_TOTAL_SIZE:
            return ToolResult(
                success=False,
                error=f"Total scratch size would exceed {MAX_TOTAL_SIZE // 1024}KB limit",
            )

        # Store
        scratch[key] = {
            "value": value,
            "description": description,
        }

        return ToolResult(
            success=True,
            result={
                "key": key,
                "stored": True,
                "keys_used": len(scratch),
                "total_size": _estimate_size(scratch),
            },
        )


# =============================================================================
# SCRATCH GET
# =============================================================================

class ScratchGetTool(BaseTool):
    """Retrieve a value from the conversation scratchpad."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="scratch_get",
            description="""Retrieve a previously stored value from the scratchpad.

Returns the value and its description if one was provided.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key of the value to retrieve",
                    },
                },
                "required": ["key"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        key = params.get("key", "")

        if not key:
            return ToolResult(success=False, error="Key is required")

        scratch = _get_scratch(context.conversation_id)

        if key not in scratch:
            return ToolResult(
                success=True,
                result={
                    "key": key,
                    "found": False,
                    "available_keys": list(scratch.keys()),
                },
            )

        entry = scratch[key]

        return ToolResult(
            success=True,
            result={
                "key": key,
                "found": True,
                "value": entry["value"],
                "description": entry.get("description"),
            },
        )


# =============================================================================
# SCRATCH LIST
# =============================================================================

class ScratchListTool(BaseTool):
    """List all keys in the conversation scratchpad."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="scratch_list",
            description="""List all keys stored in the current conversation's scratchpad.

Returns key names with their descriptions (if provided).""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        scratch = _get_scratch(context.conversation_id)

        keys = [
            {
                "key": k,
                "description": v.get("description"),
                "type": type(v["value"]).__name__,
            }
            for k, v in scratch.items()
        ]

        return ToolResult(
            success=True,
            result={
                "keys": keys,
                "count": len(keys),
                "total_size": _estimate_size(scratch),
                "size_limit": MAX_TOTAL_SIZE,
            },
        )


# =============================================================================
# SCRATCH CLEAR
# =============================================================================

class ScratchClearTool(BaseTool):
    """Clear the conversation scratchpad."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="scratch_clear",
            description="""Clear all data from the conversation scratchpad.

Use when starting a new task within the same conversation,
or to free up space for new data.

Can optionally clear only specific keys.""",
            category=ToolCategory.MEMORY,
            input_schema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific keys to delete (omit to clear all)",
                    },
                },
                "required": [],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        keys_to_delete = params.get("keys", [])

        scratch = _get_scratch(context.conversation_id)
        deleted = []

        if keys_to_delete:
            # Delete specific keys
            for key in keys_to_delete:
                if key in scratch:
                    del scratch[key]
                    deleted.append(key)
        else:
            # Clear all
            deleted = list(scratch.keys())
            scratch.clear()

        return ToolResult(
            success=True,
            result={
                "cleared": True,
                "deleted_keys": deleted,
                "deleted_count": len(deleted),
                "remaining_keys": len(scratch),
            },
        )


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(ScratchStoreTool())
registry.register(ScratchGetTool())
registry.register(ScratchListTool())
registry.register(ScratchClearTool())
