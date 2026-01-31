"""
Tier 9: Music Tools - The Creative Hands

AI music generation via Suno API.
"The artist that creates from the void"

Adapted from local ApexAurum music.py for cloud deployment.
"""

import logging
import asyncio
import re
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from enum import Enum

import httpx
from sqlalchemy import select, update

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory
from app.config import get_settings

logger = logging.getLogger(__name__)


# Suno API configuration
SUNO_API_BASE = "https://api.sunoapi.org/api/v1"

# Model character limits
MODEL_LIMITS = {
    "V3_5": {"prompt": 3000, "style": 200, "title": 80},
    "V4": {"prompt": 3000, "style": 200, "title": 80},
    "V4_5": {"prompt": 5000, "style": 1000, "title": 100},
    "V5": {"prompt": 5000, "style": 1000, "title": 100},
}


class MusicTaskStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_suno_api_key() -> Optional[str]:
    """Get Suno API key from settings."""
    settings = get_settings()
    return settings.suno_api_key


async def _submit_to_suno(
    prompt: str,
    style: str,
    title: str,
    model: str,
    is_instrumental: bool,
) -> dict:
    """Submit generation request to Suno API."""
    api_key = _get_suno_api_key()
    if not api_key:
        return {"success": False, "error": "SUNO_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "instrumental": is_instrumental,
        "customMode": True,
        "prompt": prompt,
        "callBackUrl": "https://localhost/callback",  # Placeholder, we poll instead
    }

    if title:
        payload["title"] = title[:100]
    if style:
        payload["style"] = style[:1000]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SUNO_API_BASE}/generate",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}

            result = response.json()
            if result.get("code") != 200:
                return {"success": False, "error": result.get("msg", "Unknown error")}

            suno_task_id = result.get("data", {}).get("taskId")
            if not suno_task_id:
                return {"success": False, "error": "No taskId in response"}

            return {"success": True, "suno_task_id": suno_task_id}

    except Exception as e:
        logger.exception("Suno submit error")
        return {"success": False, "error": str(e)}


async def _poll_suno_status(suno_task_id: str) -> dict:
    """Poll Suno API for task status."""
    api_key = _get_suno_api_key()
    if not api_key:
        return {"success": False, "error": "SUNO_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SUNO_API_BASE}/generate/record-info",
                headers=headers,
                params={"taskId": suno_task_id}
            )

            if response.status_code != 200:
                return {"status": "unknown", "error": f"HTTP {response.status_code}"}

            result = response.json()
            if result.get("code") != 200:
                return {"status": "unknown", "error": result.get("msg")}

            data = result.get("data", {})
            status = data.get("status", "UNKNOWN")

            if status == "PENDING":
                return {"status": "pending", "progress": "In queue..."}
            elif status == "GENERATING":
                return {"status": "generating", "progress": "Creating music..."}
            elif status == "SUCCESS":
                suno_data = data.get("response", {}).get("sunoData", [])
                if suno_data:
                    tracks = []
                    for track in suno_data:
                        tracks.append({
                            "audio_url": track.get("audioUrl"),
                            "title": track.get("title"),
                            "duration": track.get("duration", 0),
                            "clip_id": track.get("id")
                        })
                    return {"status": "completed", "tracks": tracks}
                return {"status": "failed", "error": "No audio in response"}
            elif status == "ERROR":
                return {"status": "failed", "error": data.get("error", "Generation failed")}
            else:
                return {"status": "unknown", "progress": status}

    except Exception as e:
        logger.exception("Suno poll error")
        return {"status": "unknown", "error": str(e)}


# =============================================================================
# MUSIC GENERATE
# =============================================================================

class MusicGenerateTool(BaseTool):
    """Generate AI music via Suno."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="music_generate",
            description="""Generate AI music via Suno API.

Use to:
- Create background music for projects
- Generate soundtracks based on mood/style
- Make instrumental or vocal tracks

Models: V3_5, V4, V4_5, V5 (newest/best)
Generation takes 2-4 minutes.""",
            category=ToolCategory.AGENT,  # Creative tool
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Music description. Be specific about mood, genre, instruments.",
                    },
                    "style": {
                        "type": "string",
                        "description": "Style tags (e.g., 'electronic ambient', 'jazz piano')",
                        "default": "",
                    },
                    "title": {
                        "type": "string",
                        "description": "Song title (optional)",
                        "default": "",
                    },
                    "model": {
                        "type": "string",
                        "enum": ["V3_5", "V4", "V4_5", "V5"],
                        "description": "Suno model version",
                        "default": "V5",
                    },
                    "is_instrumental": {
                        "type": "boolean",
                        "description": "True for instrumental, False for vocals",
                        "default": True,
                    },
                },
                "required": ["prompt"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        prompt = params.get("prompt", "").strip()
        style = params.get("style", "")
        title = params.get("title", "")
        model = params.get("model", "V5")
        is_instrumental = params.get("is_instrumental", True)

        if not prompt:
            return ToolResult(success=False, error="Prompt is required")

        # Validate model
        if model not in MODEL_LIMITS:
            model = "V5"

        limits = MODEL_LIMITS[model]
        if len(prompt) > limits["prompt"]:
            return ToolResult(
                success=False,
                error=f"Prompt too long ({len(prompt)} chars). Max: {limits['prompt']}"
            )

        # Check API key
        if not _get_suno_api_key():
            return ToolResult(
                success=False,
                error="SUNO_API_KEY not configured. Add it to environment variables."
            )

        try:
            from app.models.music import MusicTask
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Submit to Suno
                submit_result = await _submit_to_suno(prompt, style, title, model, is_instrumental)

                if not submit_result.get("success"):
                    return ToolResult(success=False, error=submit_result.get("error"))

                suno_task_id = submit_result["suno_task_id"]

                # Create database record
                task = MusicTask(
                    id=uuid4(),
                    user_id=user_uuid,
                    prompt=prompt,
                    style=style,
                    title=title or f"Track_{datetime.now().strftime('%H%M%S')}",
                    status="generating",
                    suno_task_id=suno_task_id,
                    agent_id=context.agent_id,
                    model=model,
                    instrumental=is_instrumental,
                )
                db.add(task)
                await db.commit()

                # Fire-and-forget background auto-completion
                import asyncio
                from app.services.suno import auto_complete_music_task
                asyncio.create_task(
                    auto_complete_music_task(str(task.id), str(user_uuid))
                )

                return ToolResult(
                    success=True,
                    result={
                        "task_id": str(task.id),
                        "suno_task_id": suno_task_id,
                        "status": "generating",
                        "model": model,
                        "is_instrumental": is_instrumental,
                        "message": "Generation started. Your song will appear in the library when ready (2-4 minutes). You can also check with music_status.",
                    },
                )

        except Exception as e:
            logger.exception("Music generate error")
            return ToolResult(success=False, error=f"Failed to start generation: {str(e)}")


# =============================================================================
# MUSIC STATUS
# =============================================================================

class MusicStatusTool(BaseTool):
    """Check music generation status."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="music_status",
            description="""Check the progress of a music generation task.

Returns status (pending/generating/completed/failed) and progress info.
If completed, includes audio URL and duration.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from music_generate",
                    },
                },
                "required": ["task_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(success=False, error="Task ID is required")

        try:
            from app.models.music import MusicTask
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                task_uuid = UUID(task_id)

                # Get task
                result = await db.execute(
                    select(MusicTask).where(
                        MusicTask.id == task_uuid,
                        MusicTask.user_id == user_uuid
                    )
                )
                task = result.scalar_one_or_none()

                if not task:
                    return ToolResult(success=False, error=f"Task not found: {task_id}")

                # If already completed/failed, return cached status
                if task.status in ("completed", "failed"):
                    return ToolResult(
                        success=True,
                        result={
                            "task_id": str(task.id),
                            "status": task.status,
                            "title": task.title,
                            "file_path": task.file_path,
                            "error": task.error,
                            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                        },
                    )

                # Poll Suno for current status
                if task.suno_task_id:
                    poll_result = await _poll_suno_status(task.suno_task_id)

                    if poll_result["status"] == "completed":
                        tracks = poll_result.get("tracks", [])
                        if tracks:
                            first_track = tracks[0]
                            task.status = "completed"
                            task.file_path = first_track.get("audio_url")
                            task.audio_url = first_track.get("audio_url")
                            task.duration = first_track.get("duration", 0.0)
                            task.clip_id = first_track.get("clip_id")
                            task.title = first_track.get("title") or task.title
                            task.completed_at = datetime.utcnow()

                            # Save additional tracks as separate entries
                            saved_alt_count = 0
                            for extra in tracks[1:]:
                                try:
                                    from app.models.music import MusicTask as MT
                                    extra_title = extra.get("title") or task.title or "Untitled"
                                    extra_task = MT(
                                        id=uuid4(),
                                        user_id=user_uuid,
                                        prompt=task.prompt,
                                        style=task.style,
                                        title=f"{extra_title} (Alt)",
                                        model=task.model,
                                        instrumental=task.instrumental,
                                        status="completed",
                                        suno_task_id=task.suno_task_id,
                                        file_path=extra.get("audio_url"),
                                        audio_url=extra.get("audio_url"),
                                        duration=extra.get("duration", 0.0),
                                        clip_id=extra.get("clip_id"),
                                        agent_id=task.agent_id,
                                        completed_at=datetime.utcnow(),
                                        progress="Complete",
                                    )
                                    db.add(extra_task)
                                    saved_alt_count += 1
                                except Exception as e:
                                    logger.warning(f"Failed to save alt track: {e}")

                            await db.commit()

                            return ToolResult(
                                success=True,
                                result={
                                    "task_id": str(task.id),
                                    "status": "completed",
                                    "title": task.title,
                                    "audio_url": first_track.get("audio_url"),
                                    "duration": first_track.get("duration"),
                                    "tracks": tracks,
                                    "track_count": len(tracks),
                                    "message": f"Generation complete! {len(tracks)} track(s) saved.",
                                },
                            )

                    elif poll_result["status"] == "failed":
                        task.status = "failed"
                        task.error = poll_result.get("error")
                        task.completed_at = datetime.utcnow()
                        await db.commit()

                        return ToolResult(
                            success=True,
                            result={
                                "task_id": str(task.id),
                                "status": "failed",
                                "error": task.error,
                            },
                        )

                    else:
                        return ToolResult(
                            success=True,
                            result={
                                "task_id": str(task.id),
                                "status": poll_result["status"],
                                "progress": poll_result.get("progress", "Processing..."),
                                "message": "Still generating. Check again in 30 seconds.",
                            },
                        )

                return ToolResult(
                    success=True,
                    result={
                        "task_id": str(task.id),
                        "status": task.status,
                        "message": "Task pending",
                    },
                )

        except Exception as e:
            logger.exception("Music status error")
            return ToolResult(success=False, error=f"Status check failed: {str(e)}")


# =============================================================================
# MUSIC LIST
# =============================================================================

class MusicListTool(BaseTool):
    """List user's music tasks."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="music_list",
            description="""List recent music generation tasks.

Shows task ID, title, status, and audio URL for each.
Useful to find previous generations.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 10)",
                        "default": 10,
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "generating", "completed", "failed"],
                        "description": "Filter by status",
                    },
                },
                "required": [],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        limit = min(params.get("limit", 10), 50)
        status_filter = params.get("status")

        try:
            from app.models.music import MusicTask
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                query = select(MusicTask).where(MusicTask.user_id == user_uuid)

                if status_filter:
                    query = query.where(MusicTask.status == status_filter)

                query = query.order_by(MusicTask.created_at.desc()).limit(limit)

                result = await db.execute(query)
                tasks = result.scalars().all()

                items = []
                for task in tasks:
                    items.append({
                        "task_id": str(task.id),
                        "title": task.title,
                        "status": task.status,
                        "audio_url": task.file_path,
                        "favorite": task.favorite,
                        "play_count": task.play_count,
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                    })

                return ToolResult(
                    success=True,
                    result={
                        "count": len(items),
                        "tasks": items,
                    },
                )

        except Exception as e:
            logger.exception("Music list error")
            return ToolResult(success=False, error=f"List failed: {str(e)}")


# =============================================================================
# MUSIC DOWNLOAD (Get Audio URL)
# =============================================================================

class MusicDownloadTool(BaseTool):
    """Get the audio URL for a completed track."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="music_download",
            description="""Get the audio URL for a completed music track.

Returns the direct URL to the audio file.
Only works for completed tasks.""",
            category=ToolCategory.AGENT,
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from music_generate",
                    },
                },
                "required": ["task_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        task_id = params.get("task_id", "")
        if not task_id:
            return ToolResult(success=False, error="Task ID is required")

        try:
            from app.models.music import MusicTask
            from app.database import async_session

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                task_uuid = UUID(task_id)

                result = await db.execute(
                    select(MusicTask).where(
                        MusicTask.id == task_uuid,
                        MusicTask.user_id == user_uuid
                    )
                )
                task = result.scalar_one_or_none()

                if not task:
                    return ToolResult(success=False, error=f"Task not found: {task_id}")

                if task.status != "completed":
                    return ToolResult(
                        success=False,
                        error=f"Task not completed. Current status: {task.status}"
                    )

                if not task.file_path:
                    return ToolResult(success=False, error="No audio URL available")

                # Increment play count
                task.play_count += 1
                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "task_id": str(task.id),
                        "title": task.title,
                        "audio_url": task.file_path,
                        "play_count": task.play_count,
                        "message": f"Audio ready: {task.title}",
                    },
                )

        except Exception as e:
            logger.exception("Music download error")
            return ToolResult(success=False, error=f"Download failed: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(MusicGenerateTool())
registry.register(MusicStatusTool())
registry.register(MusicListTool())
registry.register(MusicDownloadTool())
