"""
Tier 7: Agent Tools - The Spawning Hands

Multi-agent capabilities for complex tasks.
"Birth new agents to divide and conquer"

Allows spawning sub-agents for parallel processing,
research tasks, or specialized work.
"""

import logging
import asyncio
import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory


logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# In-memory agent task storage
# In production, this would use Redis or a task queue
_agent_tasks: dict[str, dict] = {}


async def simulate_agent_work(task_id: str, task: str, agent_type: str):
    """Simulate agent work (placeholder for real agent execution)."""
    _agent_tasks[task_id]["status"] = AgentStatus.RUNNING
    _agent_tasks[task_id]["started_at"] = datetime.now().isoformat()

    # Simulate work
    await asyncio.sleep(2)

    # For now, return a placeholder result
    _agent_tasks[task_id]["status"] = AgentStatus.COMPLETED
    _agent_tasks[task_id]["completed_at"] = datetime.now().isoformat()
    _agent_tasks[task_id]["result"] = {
        "summary": f"Agent '{agent_type}' completed task: {task[:100]}",
        "note": "This is a placeholder. Full agent execution coming soon.",
    }


# =============================================================================
# AGENT SPAWN
# =============================================================================

class AgentSpawnTool(BaseTool):
    """Spawn a sub-agent to handle a task."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="agent_spawn",
            description="""Spawn a background agent to handle a specific task.

Use for:
- Parallel research or analysis
- Delegating specialized tasks
- Breaking complex work into subtasks

The spawned agent runs asynchronously. Use agent_status to check progress
and agent_result to get the final output.

Agent types:
- research: Deep research and analysis
- code: Code generation and review
- writer: Content writing and editing
- analyst: Data analysis and insights""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for the agent",
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": ["research", "code", "writer", "analyst"],
                        "description": "Type of specialist agent to spawn",
                        "default": "research",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context for the agent",
                    },
                },
                "required": ["task"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        task = params.get("task", "")
        agent_type = params.get("agent_type", "research")
        additional_context = params.get("context", "")

        if not task:
            return ToolResult(success=False, error="Task description is required")

        if len(task) > 10000:
            return ToolResult(success=False, error="Task description exceeds 10KB limit")

        # Check concurrent agent limit
        active_count = sum(
            1 for t in _agent_tasks.values()
            if t.get("user_id") == context.user_id
            and t.get("status") in [AgentStatus.PENDING, AgentStatus.RUNNING]
        )

        if active_count >= 3:
            return ToolResult(
                success=False,
                error="Maximum 3 concurrent agents. Wait for one to complete.",
            )

        # Create task
        task_id = str(uuid.uuid4())[:8]

        _agent_tasks[task_id] = {
            "id": task_id,
            "task": task,
            "agent_type": agent_type,
            "context": additional_context,
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "status": AgentStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "result": None,
        }

        # Start agent work (non-blocking)
        asyncio.create_task(simulate_agent_work(task_id, task, agent_type))

        return ToolResult(
            success=True,
            result={
                "task_id": task_id,
                "agent_type": agent_type,
                "status": "spawned",
                "message": f"Agent '{agent_type}' spawned. Use agent_status('{task_id}') to check progress.",
            },
        )


# =============================================================================
# AGENT STATUS
# =============================================================================

class AgentStatusTool(BaseTool):
    """Check the status of a spawned agent."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="agent_status",
            description="""Check the status of a spawned agent task.

Returns:
- pending: Agent queued but not started
- running: Agent actively working
- completed: Task finished, result available
- failed: Task failed with error

Use agent_result to get the full output when status is 'completed'.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from agent_spawn",
                    },
                },
                "required": ["task_id"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        task_id = params.get("task_id", "")

        if not task_id:
            return ToolResult(success=False, error="Task ID is required")

        task = _agent_tasks.get(task_id)

        if not task:
            return ToolResult(
                success=False,
                error=f"Task '{task_id}' not found. It may have expired.",
            )

        # Verify ownership (optional security check)
        if task.get("user_id") and task["user_id"] != context.user_id:
            return ToolResult(success=False, error="Task belongs to another user")

        return ToolResult(
            success=True,
            result={
                "task_id": task_id,
                "status": task["status"],
                "agent_type": task["agent_type"],
                "created_at": task["created_at"],
                "started_at": task.get("started_at"),
                "completed_at": task.get("completed_at"),
                "has_result": task.get("result") is not None,
            },
        )


# =============================================================================
# AGENT RESULT
# =============================================================================

class AgentResultTool(BaseTool):
    """Get the result of a completed agent task."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="agent_result",
            description="""Get the full result of a completed agent task.

Only works if agent_status shows 'completed'.
Returns the agent's output, summary, and any artifacts.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from agent_spawn",
                    },
                },
                "required": ["task_id"],
            },
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        task_id = params.get("task_id", "")

        if not task_id:
            return ToolResult(success=False, error="Task ID is required")

        task = _agent_tasks.get(task_id)

        if not task:
            return ToolResult(
                success=False,
                error=f"Task '{task_id}' not found",
            )

        if task.get("user_id") and task["user_id"] != context.user_id:
            return ToolResult(success=False, error="Task belongs to another user")

        if task["status"] != AgentStatus.COMPLETED:
            return ToolResult(
                success=False,
                error=f"Task not completed. Current status: {task['status']}",
            )

        return ToolResult(
            success=True,
            result={
                "task_id": task_id,
                "agent_type": task["agent_type"],
                "task": task["task"][:200] + ("..." if len(task["task"]) > 200 else ""),
                "result": task["result"],
                "execution_time": _calculate_time(
                    task.get("started_at"),
                    task.get("completed_at")
                ),
            },
        )


def _calculate_time(start: Optional[str], end: Optional[str]) -> Optional[str]:
    """Calculate execution time between two ISO timestamps."""
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        delta = end_dt - start_dt
        return f"{delta.total_seconds():.1f}s"
    except:
        return None


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(AgentSpawnTool())
registry.register(AgentStatusTool())
registry.register(AgentResultTool())
