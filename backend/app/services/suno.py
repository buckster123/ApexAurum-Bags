"""
Suno AI Music Generation Service

The Athanor's creative voice - transforms intent into vibrating eardrums.

API: https://api.sunoapi.org/api/v1
"""

import logging
import asyncio
import aiohttp
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.music import MusicTask

logger = logging.getLogger(__name__)
settings = get_settings()

# Suno API configuration
SUNO_API_BASE = "https://api.sunoapi.org/api/v1"

# Model character limits
MODEL_LIMITS = {
    "V3_5": {"prompt": 3000, "style": 200, "title": 80},
    "V4": {"prompt": 3000, "style": 200, "title": 80},
    "V4_5": {"prompt": 5000, "style": 1000, "title": 100},
    "V5": {"prompt": 5000, "style": 1000, "title": 100},
}


class SunoService:
    """
    Suno AI music generation service.

    Handles the full pipeline:
    1. Submit generation request
    2. Poll for completion
    3. Download audio to Vault
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key = getattr(settings, 'suno_api_key', None)

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers."""
        if not self.api_key:
            raise ValueError("SUNO_API_KEY not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def generate(
        self,
        task: MusicTask,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Generate music via Suno API.

        Args:
            task: MusicTask with prompt, style, model, etc.
            progress_callback: Optional async callback(status, progress_msg)

        Returns:
            Dict with success status and audio info or error.
        """
        try:
            # Update task status
            task.status = "generating"
            task.started_at = datetime.utcnow()
            task.progress = "Submitting to Suno API..."
            await self.db.commit()

            if progress_callback:
                await progress_callback("generating", task.progress)

            # Submit to Suno
            suno_task_id = await self._submit_generation(task)
            task.suno_task_id = suno_task_id
            task.progress = "Queued at Suno..."
            await self.db.commit()

            if progress_callback:
                await progress_callback("generating", task.progress)

            # Poll for completion
            result = await self._poll_completion(task, progress_callback)

            if not result.get("success"):
                raise Exception(result.get("error", "Generation failed"))

            # Download ALL tracks (Suno generates 2 per request)
            all_tracks = result["tracks"]
            track_count = len(all_tracks)
            task.status = "downloading"
            task.progress = f"Downloading {track_count} track(s)..."
            await self.db.commit()

            if progress_callback:
                await progress_callback("downloading", task.progress)

            # Download and save primary track
            primary = all_tracks[0]
            file_path = await self._download_audio(task, primary)

            task.status = "completed"
            task.file_path = file_path
            task.audio_url = primary.get("audio_url")
            task.duration = primary.get("duration", 0.0)
            task.clip_id = primary.get("clip_id")
            task.title = primary.get("title") or task.title or f"Track_{str(task.id)[:8]}"
            task.progress = "Complete"
            task.completed_at = datetime.utcnow()
            await self.db.commit()

            # Save additional tracks as separate MusicTask entries
            extra_tasks = []
            for extra in all_tracks[1:]:
                try:
                    extra_path = await self._download_audio(task, extra)
                    extra_title = extra.get("title") or task.title or "Untitled"
                    extra_task = MusicTask(
                        id=uuid4(),
                        user_id=task.user_id,
                        prompt=task.prompt,
                        style=task.style,
                        title=f"{extra_title} (Alt)",
                        model=task.model,
                        instrumental=task.instrumental,
                        status="completed",
                        suno_task_id=task.suno_task_id,
                        file_path=extra_path,
                        audio_url=extra.get("audio_url"),
                        duration=extra.get("duration", 0.0),
                        clip_id=extra.get("clip_id"),
                        agent_id=task.agent_id,
                        completed_at=datetime.utcnow(),
                        progress="Complete",
                    )
                    self.db.add(extra_task)
                    extra_tasks.append(extra_task)
                    logger.info(f"Saved alt track: {extra_task.title} ({extra_task.id})")
                except Exception as dl_err:
                    logger.warning(f"Failed to download alt track: {dl_err}")

            if extra_tasks:
                await self.db.commit()

            if progress_callback:
                await progress_callback("completed", f"Generated: {task.title} (+{len(extra_tasks)} alt)")

            logger.info(f"Music task {task.id} completed: {task.title} ({track_count} tracks)")

            # ═══════════════════════════════════════════════════════════════════
            # VILLAGE MEMORY INJECTION - Songs become cultural memories
            # ═══════════════════════════════════════════════════════════════════
            try:
                await self._inject_village_memory(task)
            except Exception as mem_error:
                logger.warning(f"Village memory injection failed (non-fatal): {mem_error}")

            return {
                "success": True,
                "file_path": file_path,
                "audio_url": task.audio_url,
                "duration": task.duration,
                "title": task.title,
                "track_count": track_count,
            }

        except Exception as e:
            logger.error(f"Music generation failed: {e}")
            task.status = "failed"
            task.error = str(e)
            task.progress = f"Failed: {str(e)[:100]}"
            task.completed_at = datetime.utcnow()
            await self.db.commit()

            if progress_callback:
                await progress_callback("failed", task.error)

            return {"success": False, "error": str(e)}

    async def _submit_generation(self, task: MusicTask) -> str:
        """Submit generation request to Suno API."""
        headers = self._get_headers()

        payload = {
            "model": task.model,
            "instrumental": task.instrumental,
            "customMode": True,
            "prompt": task.prompt,
            "callBackUrl": "https://localhost/callback",  # Required but we poll
        }

        if task.title:
            payload["title"] = task.title[:100]
        if task.style:
            payload["style"] = task.style[:1000]

        logger.info(f"Submitting to Suno: model={task.model}, instrumental={task.instrumental}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SUNO_API_BASE}/generate",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Suno API error: HTTP {response.status}: {text[:200]}")

                result = await response.json()

                if result.get("code") != 200:
                    raise Exception(f"Suno API error: {result.get('msg', 'Unknown error')}")

                suno_task_id = result.get("data", {}).get("taskId")
                if not suno_task_id:
                    raise Exception("No taskId in Suno response")

                logger.info(f"Suno task submitted: {suno_task_id}")
                return suno_task_id

    async def _poll_completion(
        self,
        task: MusicTask,
        progress_callback: Optional[callable] = None,
        max_wait: int = 600,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Poll Suno API for completion."""
        headers = self._get_headers()
        start_time = asyncio.get_event_loop().time()

        async with aiohttp.ClientSession() as session:
            while asyncio.get_event_loop().time() - start_time < max_wait:
                try:
                    async with session.get(
                        f"{SUNO_API_BASE}/generate/record-info",
                        headers=headers,
                        params={"taskId": task.suno_task_id},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            logger.warning(f"Status check HTTP {response.status}")
                            await asyncio.sleep(poll_interval)
                            continue

                        result = await response.json()

                        if result.get("code") != 200:
                            logger.warning(f"Status API error: {result.get('msg')}")
                            await asyncio.sleep(poll_interval)
                            continue

                        data = result.get("data", {})
                        status = data.get("status", "UNKNOWN")

                        if status == "PENDING":
                            task.progress = "In queue..."
                            await self.db.commit()
                            if progress_callback:
                                await progress_callback("generating", task.progress)

                        elif status == "GENERATING":
                            task.progress = "Generating audio..."
                            await self.db.commit()
                            if progress_callback:
                                await progress_callback("generating", task.progress)

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
                                return {
                                    "success": True,
                                    "tracks": tracks,
                                    "track_count": len(tracks)
                                }
                            else:
                                return {"success": False, "error": "No audio data in response"}

                        elif status == "ERROR":
                            return {
                                "success": False,
                                "error": data.get("error", "Generation failed")
                            }

                        await asyncio.sleep(poll_interval)

                except asyncio.TimeoutError:
                    logger.warning("Poll timeout, retrying...")
                    await asyncio.sleep(poll_interval)
                except Exception as e:
                    logger.warning(f"Poll error: {e}")
                    await asyncio.sleep(poll_interval)

        return {"success": False, "error": f"Timeout after {max_wait}s"}

    async def _download_audio(self, task: MusicTask, track_info: Dict[str, Any]) -> str:
        """Download audio file to Vault."""
        audio_url = track_info.get("audio_url")
        if not audio_url:
            raise Exception("No audio URL to download")

        # Sanitize filename
        title = track_info.get("title", task.title) or f"track_{str(task.id)[:8]}"
        safe_title = re.sub(r'[^a-zA-Z0-9\s\-_]', '', title)[:60].strip() or "untitled"
        clip_id = (track_info.get("clip_id") or str(task.id))[-8:]
        filename = f"{safe_title}_{clip_id}.mp3"

        # Use Vault path for user
        vault_path = Path(settings.vault_path) / "users" / str(task.user_id) / "music"
        vault_path.mkdir(parents=True, exist_ok=True)
        filepath = vault_path / filename

        logger.info(f"Downloading audio to: {filepath}")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                audio_url,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                response.raise_for_status()

                with open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

        file_size = filepath.stat().st_size
        logger.info(f"Downloaded: {filepath} ({file_size} bytes)")

        return str(filepath)

    async def _inject_village_memory(self, task: MusicTask) -> None:
        """
        Inject completed music into Village memory.

        Creates a cultural memory that all agents can access.
        """
        from app.services.neural_memory import NeuralMemoryService

        memory_service = NeuralMemoryService(self.db)

        # Build content for the memory
        duration_str = f"{task.duration:.1f}s" if task.duration else "unknown"
        creator = task.agent_id or "User"
        prompt_preview = (task.prompt[:200] + "...") if len(task.prompt) > 200 else task.prompt

        content = f"""🎵 MUSIC CREATED: "{task.title}"
Style: {task.style or 'None specified'}
Duration: {duration_str}
Creator: {creator}
Model: {task.model}
Prompt: {prompt_preview}"""

        # Store as village-visible cultural memory
        memory_id = await memory_service.store_message(
            user_id=task.user_id,
            content=content,
            agent_id=task.agent_id or "AZOTH",
            role="assistant",  # Treat as agent observation
            visibility="village",  # Shared with all agents
            collection="music",  # Music-specific collection
        )

        if memory_id:
            logger.info(f"Injected music memory to Village: {memory_id}")
        else:
            logger.warning("Village memory injection returned None")

    async def get_task(self, task_id: UUID, user_id: UUID) -> Optional[MusicTask]:
        """Get a task by ID for user."""
        result = await self.db.execute(
            select(MusicTask)
            .where(MusicTask.id == task_id)
            .where(MusicTask.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def generate_music_stream(
    db: AsyncSession,
    task: MusicTask
) -> AsyncGenerator[str, None]:
    """
    Generate music with SSE progress streaming.

    Yields SSE events:
    - {"type": "status", "status": "...", "progress": "..."}
    - {"type": "completed", "file_path": "...", "duration": ...}
    - {"type": "error", "error": "..."}
    """
    import json

    async def progress_callback(status: str, message: str):
        event = {"type": "status", "status": status, "progress": message}
        yield f"data: {json.dumps(event)}\n\n"

    service = SunoService(db)

    # We can't use the callback directly in an async generator
    # So we'll poll the task status ourselves

    # Start generation in background
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

    if result.get("success"):
        event = {
            "type": "completed",
            "file_path": result["file_path"],
            "audio_url": result.get("audio_url"),
            "duration": result.get("duration"),
            "title": result.get("title"),
            "track_count": result.get("track_count", 1),
        }
    else:
        event = {
            "type": "error",
            "error": result.get("error", "Unknown error")
        }

    yield f"data: {json.dumps(event)}\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND AUTO-COMPLETION
# Fire-and-forget task for agent-initiated music generation.
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_complete_music_task(task_id: str, user_id: str):
    """
    Background auto-completion for agent-initiated music generation.

    Called via asyncio.create_task() after MusicGenerateTool creates the
    DB record and gets a suno_task_id. Handles the full pipeline:

    Phase 1: Poll every 15s until Suno reports SUCCESS
    Phase 2: Wait 60s for audio URLs to become downloadable
    Phase 3: Download both tracks, save to Vault, inject Village memory

    Never raises -- failures update task status but don't crash the server.
    """
    from app.database import get_db_context
    from app.tools.music import _poll_suno_status

    logger.info(f"Auto-complete started for task {task_id}")

    try:
        async with get_db_context() as db:
            # Load the task
            result = await db.execute(
                select(MusicTask)
                .where(MusicTask.id == UUID(task_id))
                .where(MusicTask.user_id == UUID(user_id))
            )
            task = result.scalar_one_or_none()

            if not task or not task.suno_task_id:
                logger.error(f"Auto-complete: task {task_id} not found or no suno_task_id")
                return

            # ═══════════════════════════════════════════════════════════════
            # Phase 1: Poll for SUCCESS status (every 15 seconds)
            # ═══════════════════════════════════════════════════════════════
            max_wait = 600  # 10 minutes
            elapsed = 0
            tracks = None

            while elapsed < max_wait:
                poll_result = await _poll_suno_status(task.suno_task_id)

                if poll_result["status"] == "completed":
                    tracks = poll_result.get("tracks", [])
                    task.progress = "Audio ready, preparing download..."
                    await db.commit()
                    logger.info(f"Auto-complete: Suno SUCCESS for task {task_id} ({len(tracks)} tracks)")
                    break

                elif poll_result["status"] == "failed":
                    task.status = "failed"
                    task.error = poll_result.get("error", "Generation failed")
                    task.progress = f"Failed: {task.error[:100]}"
                    task.completed_at = datetime.utcnow()
                    await db.commit()
                    logger.warning(f"Auto-complete: Suno FAILED for task {task_id}: {task.error}")
                    return

                else:
                    task.progress = poll_result.get("progress", "Processing...")
                    await db.commit()

                await asyncio.sleep(15)
                elapsed += 15

            if not tracks:
                task.status = "failed"
                task.error = f"Timeout after {max_wait}s waiting for Suno"
                task.progress = "Timed out"
                task.completed_at = datetime.utcnow()
                await db.commit()
                logger.warning(f"Auto-complete: timeout for task {task_id}")
                return

            # ═══════════════════════════════════════════════════════════════
            # Phase 2: Wait 60s for audio URLs to stabilize
            # ═══════════════════════════════════════════════════════════════
            task.progress = "Waiting for audio to finalize..."
            await db.commit()
            await asyncio.sleep(60)

            # ═══════════════════════════════════════════════════════════════
            # Phase 3: Download tracks to Vault
            # ═══════════════════════════════════════════════════════════════
            service = SunoService(db)

            # Download primary track (retry up to 3 times)
            primary = tracks[0]
            file_path = None
            for attempt in range(3):
                try:
                    task.progress = f"Downloading track 1/{len(tracks)}..."
                    await db.commit()
                    file_path = await service._download_audio(task, primary)
                    break
                except Exception as dl_err:
                    logger.warning(f"Auto-complete: download attempt {attempt+1} failed: {dl_err}")
                    if attempt < 2:
                        await asyncio.sleep(15)

            if not file_path:
                # Fallback: store CDN URL directly
                file_path = primary.get("audio_url", "")
                logger.warning(f"Auto-complete: using CDN URL fallback for task {task_id}")

            # Update primary task
            task.status = "completed"
            task.file_path = file_path
            task.audio_url = primary.get("audio_url")
            task.duration = primary.get("duration", 0.0)
            task.clip_id = primary.get("clip_id")
            task.title = primary.get("title") or task.title or f"Track_{task_id[:8]}"
            task.progress = "Complete"
            task.completed_at = datetime.utcnow()
            await db.commit()

            # Download and save alt tracks
            for i, extra in enumerate(tracks[1:], 2):
                try:
                    task.progress = f"Downloading track {i}/{len(tracks)}..."
                    await db.commit()
                    extra_path = await service._download_audio(task, extra)
                    extra_title = extra.get("title") or task.title or "Untitled"
                    extra_task = MusicTask(
                        id=uuid4(),
                        user_id=task.user_id,
                        prompt=task.prompt,
                        style=task.style,
                        title=f"{extra_title} (Alt)",
                        model=task.model,
                        instrumental=task.instrumental,
                        status="completed",
                        suno_task_id=task.suno_task_id,
                        file_path=extra_path,
                        audio_url=extra.get("audio_url"),
                        duration=extra.get("duration", 0.0),
                        clip_id=extra.get("clip_id"),
                        agent_id=task.agent_id,
                        completed_at=datetime.utcnow(),
                        progress="Complete",
                    )
                    db.add(extra_task)
                    logger.info(f"Auto-complete: saved alt track {extra_task.id}")
                except Exception as dl_err:
                    logger.warning(f"Auto-complete: alt track download failed: {dl_err}")

            await db.commit()

            # ═══════════════════════════════════════════════════════════════
            # Village memory injection
            # ═══════════════════════════════════════════════════════════════
            try:
                await service._inject_village_memory(task)
            except Exception as mem_err:
                logger.warning(f"Auto-complete: village memory failed (non-fatal): {mem_err}")

            # ═══════════════════════════════════════════════════════════════
            # WebSocket broadcast -- notify all connected clients
            # ═══════════════════════════════════════════════════════════════
            try:
                from app.services.village_events import get_village_broadcaster, VillageEvent, EventType
                broadcaster = get_village_broadcaster()
                event = VillageEvent(
                    type=EventType.MUSIC_COMPLETE,
                    agent_id=task.agent_id or "SYSTEM",
                    tool="music_generate",
                    zone="dj_booth",
                    message=f"Song ready: {task.title}",
                )
                await broadcaster.broadcast(event)
            except Exception as ws_err:
                logger.warning(f"Auto-complete: WebSocket broadcast failed (non-fatal): {ws_err}")

            logger.info(f"Auto-complete DONE: task {task_id} - '{task.title}' ({len(tracks)} tracks)")

    except Exception as e:
        logger.error(f"Auto-complete FATAL for task {task_id}: {e}")
        try:
            from app.database import get_db_context as _get_db
            async with _get_db() as db:
                result = await db.execute(
                    select(MusicTask).where(MusicTask.id == UUID(task_id))
                )
                task = result.scalar_one_or_none()
                if task and task.status != "completed":
                    task.status = "failed"
                    task.error = f"Auto-complete error: {str(e)[:200]}"
                    task.completed_at = datetime.utcnow()
                    await db.commit()
        except Exception:
            logger.error(f"Auto-complete: couldn't mark task {task_id} as failed")
