"""
Tier 14: Jam Session Tools - The Village Band

Collaborative music creation tools for multi-agent composition.

Tools:
- jam_create: Start a new jam session
- jam_contribute: Add notes to your track
- jam_listen: See what others have contributed
- jam_finalize: Compile all tracks and send to Suno

"The Band plays as one"
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory

logger = logging.getLogger(__name__)


# Default role assignments
DEFAULT_ROLES = {
    "AZOTH": "producer",
    "ELYSIAN": "melody",
    "VAJRA": "bass",
    "KETHER": "harmony",
}


# =============================================================================
# JAM CREATE
# =============================================================================

class JamCreateTool(BaseTool):
    """Create a new jam session for collaborative composition."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="jam_create",
            description="""Create a new Village Band jam session for collaborative music composition.

Multiple agents contribute notes in their assigned roles:
- AZOTH: Producer (oversees, finalizes)
- ELYSIAN: Melody (lead voice, themes)
- VAJRA: Bass (low-end foundation)
- KETHER: Harmony (chords, textures)

Example:
>>> jam_create(title="Cosmic Journey", style="ethereal ambient space", tempo=70, key="Am")
>>> # Returns session_id for contributing notes""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Name for the jam session",
                        "default": "Untitled Jam",
                    },
                    "style": {
                        "type": "string",
                        "description": "Target style for Suno (e.g., 'ethereal ambient', 'dark electronic')",
                    },
                    "tempo": {
                        "type": "integer",
                        "description": "Beats per minute",
                        "default": 120,
                    },
                    "key": {
                        "type": "string",
                        "description": "Musical key (C, Am, F#m, etc.)",
                        "default": "C",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["conductor", "jam", "auto"],
                        "description": "Interaction mode: conductor (user directs), jam (collaborative), auto (full freedom)",
                        "default": "jam",
                    },
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Agents to include (default: all native agents)",
                    },
                    "max_rounds": {
                        "type": "integer",
                        "description": "Maximum contribution rounds",
                        "default": 5,
                    },
                    "inspiration": {
                        "type": "string",
                        "description": "Initial creative seed or theme",
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
            from app.models.jam import JamSession, JamParticipant, JamMode, JamState, DEFAULT_AGENT_ROLES
            from app.database import async_session

            title = params.get("title", "Untitled Jam")
            style = params.get("style")
            tempo = params.get("tempo", 120)
            key = params.get("key", "C")
            mode = params.get("mode", "jam")
            agents = params.get("agents", ["AZOTH", "ELYSIAN", "VAJRA", "KETHER"])
            max_rounds = params.get("max_rounds", 5)
            inspiration = params.get("inspiration")

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                # Create session
                session = JamSession(
                    id=uuid4(),
                    user_id=user_uuid,
                    title=title,
                    style=style,
                    tempo=tempo,
                    musical_key=key,
                    mode=mode,
                    state=JamState.FORMING.value,
                    max_rounds=max_rounds,
                    inspiration=inspiration,
                )
                db.add(session)
                await db.flush()

                # Create participants with roles
                participants_info = []
                for agent_id in agents:
                    role = DEFAULT_AGENT_ROLES.get(agent_id, "free").value if hasattr(DEFAULT_AGENT_ROLES.get(agent_id, "free"), 'value') else DEFAULT_ROLES.get(agent_id, "free")
                    participant = JamParticipant(
                        id=uuid4(),
                        session_id=session.id,
                        agent_id=agent_id,
                        role=role,
                        display_name=agent_id,
                    )
                    db.add(participant)
                    participants_info.append({"agent": agent_id, "role": role})

                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "session_id": str(session.id),
                        "title": title,
                        "style": style,
                        "tempo": tempo,
                        "key": key,
                        "mode": mode,
                        "participants": participants_info,
                        "max_rounds": max_rounds,
                        "message": f"🎸 Village Band assembled! Session '{title}' ready. Use jam_contribute() to add your notes.",
                    },
                )

        except Exception as e:
            logger.exception("Jam create error")
            return ToolResult(success=False, error=f"Failed to create jam session: {str(e)}")


# =============================================================================
# JAM CONTRIBUTE
# =============================================================================

class JamContributeTool(BaseTool):
    """Contribute notes to a jam session."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="jam_contribute",
            description="""Add notes to your track in a jam session.

Notes can be:
- Note names: 'C4', 'F#3', 'Bb5'
- MIDI numbers: 60, 64, 67
- Rests: 'R' or 0

Example:
>>> jam_contribute(
...     session_id="...",
...     notes=["A3", "C4", "E4", "A4"],  # A minor arpeggio
...     description="A haunting ascending phrase"
... )""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The jam session ID",
                    },
                    "notes": {
                        "type": "array",
                        "items": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
                        "description": "Notes to contribute: 'C4', 'F#3', 60, etc. Use 'R' for rests.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Describe your musical intention",
                    },
                    "duration": {
                        "type": "number",
                        "description": "Duration per note in beats (0.5 = eighth, 1.0 = quarter)",
                        "default": 0.5,
                    },
                    "velocity": {
                        "type": "integer",
                        "description": "Note velocity/loudness (0-127)",
                        "default": 100,
                    },
                },
                "required": ["session_id", "notes"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        session_id = params.get("session_id")
        notes = params.get("notes", [])
        description = params.get("description")
        duration = params.get("duration", 0.5)
        velocity = params.get("velocity", 100)

        if not session_id:
            return ToolResult(success=False, error="session_id is required")
        if not notes:
            return ToolResult(success=False, error="notes array is required")

        try:
            from app.models.jam import JamSession, JamParticipant, JamTrack, JamState
            from app.database import async_session
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                session_uuid = UUID(session_id)

                # Get session
                result = await db.execute(
                    select(JamSession)
                    .where(JamSession.id == session_uuid)
                    .where(JamSession.user_id == user_uuid)
                    .options(selectinload(JamSession.participants))
                )
                session = result.scalar_one_or_none()

                if not session:
                    return ToolResult(success=False, error="Jam session not found")

                if session.state not in (JamState.JAMMING.value, JamState.FORMING.value):
                    return ToolResult(
                        success=False,
                        error=f"Cannot contribute in state: {session.state}"
                    )

                # Auto-start if forming
                if session.state == JamState.FORMING.value:
                    session.state = JamState.JAMMING.value
                    session.started_at = datetime.utcnow()
                    session.current_round = 1

                # Find or use agent from context
                agent_id = context.agent_id or "UNKNOWN"
                participant = next(
                    (p for p in session.participants if p.agent_id == agent_id),
                    None
                )

                if not participant:
                    # Auto-add as free role
                    participant = JamParticipant(
                        id=uuid4(),
                        session_id=session.id,
                        agent_id=agent_id,
                        role="free",
                        display_name=agent_id,
                    )
                    db.add(participant)
                    await db.flush()

                # Build note objects with timing
                note_objects = []
                current_time = 0.0
                for note in notes:
                    note_obj = {
                        "note": str(note),
                        "time": current_time,
                        "duration": duration,
                        "velocity": velocity,
                    }
                    note_objects.append(note_obj)
                    current_time += duration

                # Create track
                track = JamTrack(
                    id=uuid4(),
                    session_id=session.id,
                    agent_id=agent_id,
                    role=participant.role,
                    round_number=session.current_round,
                    notes=note_objects,
                    description=description,
                )
                db.add(track)

                # Update participant stats
                participant.contributions += 1
                participant.total_notes += len(notes)
                participant.last_contribution_at = datetime.utcnow()

                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "track_id": str(track.id),
                        "agent_id": agent_id,
                        "role": participant.role,
                        "note_count": len(notes),
                        "round": session.current_round,
                        "total_contributions": participant.contributions,
                        "message": f"🎵 Added {len(notes)} notes to the jam! ({description or 'No description'})",
                    },
                )

        except Exception as e:
            logger.exception("Jam contribute error")
            return ToolResult(success=False, error=f"Failed to contribute: {str(e)}")


# =============================================================================
# JAM LISTEN
# =============================================================================

class JamListenTool(BaseTool):
    """See what others have contributed to a jam session."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="jam_listen",
            description="""Listen to what others have contributed in the jam session.

Returns all tracks with notes and descriptions so you can build on them.""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The jam session ID",
                    },
                    "round": {
                        "type": "integer",
                        "description": "Specific round to view (optional, defaults to all)",
                    },
                },
                "required": ["session_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        session_id = params.get("session_id")
        round_filter = params.get("round")

        if not session_id:
            return ToolResult(success=False, error="session_id is required")

        try:
            from app.models.jam import JamSession, JamTrack
            from app.database import async_session
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id
                session_uuid = UUID(session_id)

                result = await db.execute(
                    select(JamSession)
                    .where(JamSession.id == session_uuid)
                    .where(JamSession.user_id == user_uuid)
                    .options(
                        selectinload(JamSession.tracks),
                        selectinload(JamSession.participants),
                    )
                )
                session = result.scalar_one_or_none()

                if not session:
                    return ToolResult(success=False, error="Jam session not found")

                # Filter tracks
                tracks = session.tracks
                if round_filter:
                    tracks = [t for t in tracks if t.round_number == round_filter]

                # Build contribution summary
                contributions = []
                for track in sorted(tracks, key=lambda t: (t.round_number, t.created_at)):
                    note_preview = [n.get("note") for n in (track.notes or [])[:8]]
                    if len(track.notes or []) > 8:
                        note_preview.append("...")

                    contributions.append({
                        "agent": track.agent_id,
                        "role": track.role,
                        "round": track.round_number,
                        "notes": note_preview,
                        "note_count": len(track.notes or []),
                        "description": track.description,
                    })

                participants = [
                    {
                        "agent": p.agent_id,
                        "role": p.role,
                        "contributions": p.contributions,
                        "total_notes": p.total_notes,
                    }
                    for p in session.participants
                ]

                return ToolResult(
                    success=True,
                    result={
                        "session_id": str(session.id),
                        "title": session.title,
                        "style": session.style,
                        "tempo": session.tempo,
                        "key": session.musical_key,
                        "current_round": session.current_round,
                        "state": session.state,
                        "participants": participants,
                        "contributions": contributions,
                        "total_tracks": len(session.tracks),
                        "message": f"🎧 Listening to '{session.title}' - {len(contributions)} contributions so far",
                    },
                )

        except Exception as e:
            logger.exception("Jam listen error")
            return ToolResult(success=False, error=f"Failed to listen: {str(e)}")


# =============================================================================
# JAM FINALIZE
# =============================================================================

class JamFinalizeTool(BaseTool):
    """Finalize the jam session and generate music via Suno."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="jam_finalize",
            description="""Finalize the jam session: merge all tracks into MIDI and transform via Suno.

This is typically called by the producer (AZOTH) when the band has contributed enough.
The audio_influence parameter controls how much Suno follows the MIDI composition.""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The jam session ID",
                    },
                    "audio_influence": {
                        "type": "number",
                        "description": "How much MIDI affects Suno output (0.0-1.0). 0.5 is balanced.",
                        "default": 0.5,
                    },
                    "style_override": {
                        "type": "string",
                        "description": "Override the session style for final generation",
                    },
                    "title_override": {
                        "type": "string",
                        "description": "Override the session title for final track",
                    },
                },
                "required": ["session_id"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        session_id = params.get("session_id")
        audio_influence = params.get("audio_influence", 0.5)
        style_override = params.get("style_override")
        title_override = params.get("title_override")

        if not session_id:
            return ToolResult(success=False, error="session_id is required")

        try:
            import httpx
            from app.config import get_settings

            settings = get_settings()
            user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

            # Call the finalize API endpoint (reuse the logic there)
            # This is a bit of a shortcut - in production you might want to
            # share the logic more directly, but this keeps things DRY
            async with httpx.AsyncClient(timeout=300.0) as client:
                # We need an auth token - this is a tool context, so we'll
                # call the internal logic directly instead

                from app.models.jam import JamSession, JamState
                from app.models.music import MusicTask
                from app.database import async_session
                from app.services.midi import MidiService
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload

                async with async_session() as db:
                    result = await db.execute(
                        select(JamSession)
                        .where(JamSession.id == UUID(session_id))
                        .where(JamSession.user_id == user_uuid)
                        .options(
                            selectinload(JamSession.tracks),
                            selectinload(JamSession.participants),
                        )
                    )
                    session = result.scalar_one_or_none()

                    if not session:
                        return ToolResult(success=False, error="Session not found")

                    if not session.tracks:
                        return ToolResult(
                            success=False,
                            error="No tracks to finalize. The band needs to contribute first!"
                        )

                    # Group tracks by agent for multi-track MIDI layering
                    tracks_by_agent = {}
                    for track in sorted(session.tracks, key=lambda t: (t.round_number, t.created_at)):
                        if not track.notes:
                            continue
                        aid = track.agent_id or "UNKNOWN"
                        if aid not in tracks_by_agent:
                            tracks_by_agent[aid] = []
                        tracks_by_agent[aid].append({
                            "round_number": track.round_number,
                            "notes": track.notes,
                        })

                    if not tracks_by_agent:
                        return ToolResult(success=False, error="No notes in tracks")

                    # Create layered MIDI (each agent on its own track)
                    midi_service = MidiService()
                    midi_result = await midi_service.create_layered_midi(
                        tracks_by_agent=tracks_by_agent,
                        tempo=session.tempo,
                        title=title_override or session.title,
                        user_id=str(user_uuid),
                    )

                    if not midi_result.get("success"):
                        return ToolResult(
                            success=False,
                            error=f"MIDI creation failed: {midi_result.get('error')}"
                        )

                    session.final_midi_path = midi_result["midi_file"]
                    session.state = JamState.FINALIZING.value
                    session.audio_influence = audio_influence

                    # Check dependencies
                    deps = midi_service.check_dependencies()
                    if not deps["ready"]:
                        session.state = JamState.COMPLETE.value
                        session.completed_at = datetime.utcnow()
                        await db.commit()

                        return ToolResult(
                            success=True,
                            result={
                                "midi_file": midi_result["midi_file"],
                                "note_count": midi_result.get("note_count", 0),
                                "track_count": midi_result.get("track_count", 1),
                                "message": f"🎼 MIDI created with {midi_result.get('note_count', 0)} notes across {midi_result.get('track_count', 1)} tracks! (Suno composition skipped - FluidSynth not available)",
                                "dependencies_missing": [k for k, v in deps.items() if not v and k != "ready"],
                            },
                        )

                    # Full pipeline
                    audio_result = await midi_service.midi_to_audio(midi_result["midi_file"])
                    if not audio_result.get("success"):
                        return ToolResult(
                            success=False,
                            error=f"Audio conversion failed: {audio_result.get('error')}"
                        )

                    upload_result = await midi_service.upload_to_suno(audio_result["audio_path"])
                    if not upload_result.get("success"):
                        return ToolResult(
                            success=False,
                            error=f"Upload failed: {upload_result.get('error')}"
                        )

                    style = style_override or session.style or "collaborative composition"
                    title = title_override or session.title

                    cover_result = await midi_service.call_upload_cover(
                        upload_url=upload_result["upload_url"],
                        style=style,
                        title=title,
                        audio_weight=audio_influence,
                        instrumental=True,
                    )

                    if not cover_result.get("success"):
                        return ToolResult(
                            success=False,
                            error=f"Suno cover failed: {cover_result.get('error')}"
                        )

                    # Create music task
                    participant_names = ", ".join(p.agent_id for p in session.participants)
                    music_task = MusicTask(
                        id=uuid4(),
                        user_id=user_uuid,
                        prompt=f"[VILLAGE BAND] {title} - by {participant_names}",
                        style=style,
                        title=title,
                        model="V5",
                        instrumental=True,
                        status="generating",
                        progress="Village Band masterpiece in progress...",
                        suno_task_id=cover_result["suno_task_id"],
                        agent_id="VILLAGE_BAND",
                    )
                    db.add(music_task)

                    session.final_music_task_id = music_task.id
                    session.state = JamState.COMPLETE.value
                    session.completed_at = datetime.utcnow()
                    await db.commit()

                    # Fire auto-completion background worker
                    import asyncio
                    from app.services.suno import auto_complete_music_task
                    asyncio.create_task(
                        auto_complete_music_task(str(music_task.id), str(user_uuid))
                    )

                    return ToolResult(
                        success=True,
                        result={
                            "music_task_id": str(music_task.id),
                            "midi_file": midi_result["midi_file"],
                            "note_count": midi_result.get("note_count", 0),
                            "track_count": midi_result.get("track_count", 1),
                            "audio_influence": audio_influence,
                            "style": style,
                            "title": title,
                            "participants": participant_names,
                            "message": f"🎸 The Village Band has spoken! '{title}' is being forged. It will appear in the library when ready.",
                        },
                    )

        except Exception as e:
            logger.exception("Jam finalize error")
            return ToolResult(success=False, error=f"Failed to finalize: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(JamCreateTool())
registry.register(JamContributeTool())
registry.register(JamListenTool())
registry.register(JamFinalizeTool())
