"""
Music API Endpoints

AI music generation via Suno - The Athanor's creative voice.

Supports:
- music_generate: Start generation (sync or SSE stream)
- music_status: Check progress
- music_library: Browse with filters
- music_play: Increment play count, return file
- music_favorite: Toggle favorite
"""

import logging
import asyncio
import json
from typing import Optional
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.music import MusicTask
from app.auth.deps import get_current_user, get_current_user_optional
from app.services.suno import SunoService

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class MusicGenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    title: Optional[str] = None
    model: str = "V5"  # V3_5, V4, V4_5, V5
    instrumental: bool = True
    agent_id: Optional[str] = None  # Which agent requested generation
    stream: bool = False  # SSE streaming


class MusicTaskResponse(BaseModel):
    id: UUID
    prompt: str
    style: Optional[str]
    title: Optional[str]
    model: str
    instrumental: bool
    status: str
    progress: Optional[str]
    file_path: Optional[str]
    audio_url: Optional[str]
    duration: Optional[float]
    error: Optional[str]
    favorite: bool
    play_count: int
    agent_id: Optional[str]
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class MusicLibraryResponse(BaseModel):
    tasks: list[MusicTaskResponse]
    total: int
    total_duration: float


class MusicPlayResponse(BaseModel):
    id: UUID
    title: Optional[str]
    file_path: str
    duration: Optional[float]
    play_count: int


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

def task_to_response(task: MusicTask) -> MusicTaskResponse:
    """Convert MusicTask to response model."""
    return MusicTaskResponse(
        id=task.id,
        prompt=task.prompt,
        style=task.style,
        title=task.title,
        model=task.model,
        instrumental=task.instrumental,
        status=task.status,
        progress=task.progress,
        file_path=task.file_path,
        audio_url=task.audio_url,
        duration=task.duration,
        error=task.error,
        favorite=task.favorite,
        play_count=task.play_count,
        agent_id=task.agent_id,
        created_at=task.created_at.isoformat(),
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


async def run_generation(db: AsyncSession, task_id: UUID, user_id: UUID):
    """Background task for music generation."""
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        logger.error(f"Task {task_id} not found for generation")
        return

    service = SunoService(db)
    await service.generate(task)


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/generate")
async def generate_music(
    request: MusicGenerateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate music using Suno AI.

    If stream=False (default): Returns task immediately, generation runs in background.
    If stream=True: Returns SSE stream with real-time progress updates.

    Models:
    - V3_5: Fast, lower quality
    - V4: Balanced
    - V4_5: Better quality
    - V5: Best quality (recommended)
    """
    # Check suno generation limit
    from app.config import TIER_LIMITS
    from app.models.billing import Subscription
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])
    suno_limit = tier_config.get("suno_generations_per_month")
    if suno_limit is not None:
        if suno_limit == 0:
            raise HTTPException(status_code=403, detail="Music generation is not available on your current plan. Upgrade to Seeker ($10/mo).")
        from app.services.usage import UsageService
        usage_service = UsageService(db)
        allowed, current, limit = await usage_service.check_usage_limit(user.id, "suno_generations", suno_limit)
        if not allowed:
            raise HTTPException(status_code=403, detail=f"Suno generation limit reached ({current}/{limit} this month). Upgrade for more.")

    # Check API key is configured
    if not getattr(settings, 'suno_api_key', None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Music generation not configured. SUNO_API_KEY required."
        )

    # Create task record
    task = MusicTask(
        user_id=user.id,
        prompt=request.prompt,
        style=request.style,
        title=request.title,
        model=request.model,
        instrumental=request.instrumental,
        agent_id=request.agent_id,
        status="pending",
        progress="Queued",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Increment suno generation counter and deduct feature credit if over limit
    try:
        from app.services.usage import UsageService
        usage_service = UsageService(db)
        await usage_service.increment_usage(user.id, "suno_generations")
        if suno_limit is not None and suno_limit > 0:
            await usage_service.deduct_feature_credit_if_over_limit(
                user.id, "suno_generations", suno_limit
            )
    except Exception as e:
        logger.warning(f"Suno counter/credit deduction failed (non-fatal): {e}")

    if request.stream:
        # SSE streaming response
        async def generate_stream():
            service = SunoService(db)

            # Start generation
            generation_task = asyncio.create_task(service.generate(task))

            last_progress = None
            while not generation_task.done():
                # Refresh task from DB
                await db.refresh(task)

                if task.progress != last_progress:
                    last_progress = task.progress
                    event = {
                        "type": "status",
                        "status": task.status,
                        "progress": task.progress or ""
                    }
                    yield f"data: {json.dumps(event)}\n\n"

                await asyncio.sleep(1)

            # Get final result
            result = await generation_task
            await db.refresh(task)

            if result.get("success"):
                event = {
                    "type": "completed",
                    "task": task_to_response(task).model_dump(mode="json"),
                }
            else:
                event = {
                    "type": "error",
                    "error": result.get("error", "Unknown error"),
                    "task_id": str(task.id),
                }

            yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # Background generation - return immediately
        background_tasks.add_task(run_generation, db, task.id, user.id)

        return task_to_response(task)


@router.get("/library", response_model=MusicLibraryResponse)
async def get_library(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    favorites_only: bool = False,
    agent_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, max_length=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get music library with filters.

    Filters:
    - favorites_only: Only favorited tracks
    - agent_id: Filter by creator agent
    - status: Filter by status (pending, generating, completed, failed)
    - search: Search in title, prompt, style
    """
    query = select(MusicTask).where(MusicTask.user_id == user.id)

    if favorites_only:
        query = query.where(MusicTask.favorite == True)
    if agent_id:
        query = query.where(MusicTask.agent_id == agent_id)
    if status_filter:
        query = query.where(MusicTask.status == status_filter)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (MusicTask.title.ilike(search_pattern)) |
            (MusicTask.prompt.ilike(search_pattern)) |
            (MusicTask.style.ilike(search_pattern))
        )

    query = query.order_by(MusicTask.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    tasks = result.scalars().all()

    # Get total count
    count_query = select(func.count(MusicTask.id)).where(MusicTask.user_id == user.id)
    if favorites_only:
        count_query = count_query.where(MusicTask.favorite == True)
    if agent_id:
        count_query = count_query.where(MusicTask.agent_id == agent_id)
    if status_filter:
        count_query = count_query.where(MusicTask.status == status_filter)
    if search:
        count_query = count_query.where(
            (MusicTask.title.ilike(search_pattern)) |
            (MusicTask.prompt.ilike(search_pattern)) |
            (MusicTask.style.ilike(search_pattern))
        )

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Calculate total duration
    total_duration = sum(t.duration or 0 for t in tasks if t.status == "completed")

    return MusicLibraryResponse(
        tasks=[task_to_response(t) for t in tasks],
        total=total,
        total_duration=total_duration,
    )


@router.get("/tasks/{task_id}", response_model=MusicTaskResponse)
async def get_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get music task status and details."""
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music task not found"
        )

    return task_to_response(task)


@router.get("/tasks/{task_id}/file")
async def get_audio_file(
    task_id: UUID,
    token: Optional[str] = Query(None, description="JWT token for audio playback (alt to header)"),
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the audio file for a completed task.

    Returns the MP3 file directly for playback.

    Accepts auth via:
    - Authorization header (standard)
    - ?token= query param (for HTML audio elements)
    """
    # Handle token query param auth (for audio elements that can't send headers)
    if user is None and token:
        from app.auth.jwt import verify_token
        from sqlalchemy import select
        payload = verify_token(token, token_type="access")
        if payload:
            try:
                user_id = UUID(payload["sub"])
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
            except (KeyError, ValueError, TypeError):
                pass

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music task not found"
        )

    if task.status != "completed" or not task.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Music not ready. Status: {task.status}"
        )

    # If file_path is a URL (agent-polled tracks store Suno CDN URL),
    # redirect to it directly instead of trying to serve from disk
    if task.file_path.startswith("http"):
        return RedirectResponse(url=task.file_path)

    file_path = Path(task.file_path)
    if not file_path.exists():
        # Fallback: if audio_url exists, redirect to CDN
        if task.audio_url:
            return RedirectResponse(url=task.audio_url)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found on disk"
        )

    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        filename=file_path.name,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{file_path.name}"',
        }
    )


@router.post("/tasks/{task_id}/play", response_model=MusicPlayResponse)
async def play_track(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a track as played (increments play count).

    Returns file path and updated play count.
    """
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music task not found"
        )

    if task.status != "completed" or not task.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Track not ready. Status: {task.status}"
        )

    task.play_count += 1
    await db.commit()

    return MusicPlayResponse(
        id=task.id,
        title=task.title,
        file_path=task.file_path,
        duration=task.duration,
        play_count=task.play_count,
    )


@router.patch("/tasks/{task_id}/favorite")
async def toggle_favorite(
    task_id: UUID,
    favorite: bool,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle favorite status for a track."""
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music task not found"
        )

    task.favorite = favorite
    await db.commit()

    return {
        "id": str(task.id),
        "favorite": favorite,
        "title": task.title,
    }


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a music task and its audio file."""
    result = await db.execute(
        select(MusicTask)
        .where(MusicTask.id == task_id)
        .where(MusicTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music task not found"
        )

    # Delete audio file if exists
    if task.file_path:
        try:
            file_path = Path(task.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted audio file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete audio file: {e}")

    await db.delete(task)
    await db.commit()

    return {"message": "Task deleted", "id": str(task_id)}


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostic Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/diagnostic")
async def music_diagnostic():
    """Check music service configuration."""
    has_api_key = bool(getattr(settings, 'suno_api_key', None))

    return {
        "service": "suno",
        "configured": has_api_key,
        "api_base": "https://api.sunoapi.org/api/v1",
        "models": ["V3_5", "V4", "V4_5", "V5"],
        "vault_path": str(settings.vault_path),
        "message": "Ready" if has_api_key else "SUNO_API_KEY not configured",
    }
