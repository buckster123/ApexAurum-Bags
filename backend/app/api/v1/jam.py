"""
Jam Session API - The Athanor's Band Studio

Multi-agent collaborative music composition endpoints.

Endpoints:
- POST /jam/sessions - Create a jam session
- GET /jam/sessions - List user's jam sessions
- GET /jam/sessions/{id} - Get session details with tracks
- POST /jam/sessions/{id}/contribute - Add notes to a track
- POST /jam/sessions/{id}/finalize - Merge tracks and send to Suno
- DELETE /jam/sessions/{id} - Delete a session
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.jam import (
    JamSession, JamParticipant, JamTrack, JamMessage,
    JamMode, JamState, JamRole, DEFAULT_AGENT_ROLES
)
from app.auth.deps import get_current_user
from app.services.midi import MidiService
from app.services.claude import ClaudeService
from app.services.tool_executor import create_tool_executor
from app.services.neural_memory import NeuralMemoryService
from app.api.v1.chat import load_native_prompt, get_agent_prompt_with_memory
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/jam", tags=["Jam Sessions"])


# ============================================================================
# Schemas
# ============================================================================

class CreateJamRequest(BaseModel):
    """Request to create a new jam session."""
    title: Optional[str] = "Untitled Jam"
    style: Optional[str] = None  # Target style for Suno
    tempo: int = 120  # BPM
    musical_key: str = "C"  # Musical key
    mode: str = "jam"  # conductor, jam, auto
    agents: List[str] = ["AZOTH", "ELYSIAN", "VAJRA", "KETHER"]
    max_rounds: int = 5
    inspiration: Optional[str] = None  # Initial prompt/seed


class ContributeRequest(BaseModel):
    """Request to contribute notes to a track."""
    agent_id: str
    notes: List[dict]  # [{note: 'C4', time: 0, duration: 0.5, velocity: 100}, ...]
    description: Optional[str] = None  # Agent's description of contribution
    role: Optional[str] = None  # Override role for this contribution


class FinalizeRequest(BaseModel):
    """Request to finalize and generate music."""
    audio_influence: float = 0.5  # How much MIDI affects Suno output
    style_override: Optional[str] = None  # Override session style
    title_override: Optional[str] = None  # Override session title


class NoteInfo(BaseModel):
    """A single note in a track."""
    note: str  # 'C4', 'F#3', etc.
    time: float  # Start time in beats
    duration: float  # Duration in beats
    velocity: int = 100  # 0-127


class TrackResponse(BaseModel):
    """Response for a single track."""
    id: UUID
    agent_id: str
    role: str
    round_number: int
    notes: List[dict]
    description: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ParticipantResponse(BaseModel):
    """Response for a participant."""
    id: UUID
    agent_id: str
    role: str
    display_name: Optional[str]
    contributions: int
    total_notes: int
    is_active: bool

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Response for a jam message."""
    id: UUID
    agent_id: str
    content: str
    round_number: int
    track_id: Optional[UUID]
    created_at: str

    class Config:
        from_attributes = True


class JamSessionResponse(BaseModel):
    """Response for a jam session."""
    id: UUID
    title: str
    style: Optional[str]
    tempo: int
    musical_key: str
    mode: str
    state: str
    current_round: int
    max_rounds: int
    inspiration: Optional[str]
    audio_influence: float
    final_music_task_id: Optional[UUID]
    participants: List[ParticipantResponse]
    tracks: List[TrackResponse]
    messages: List[MessageResponse]
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class JamSessionListItem(BaseModel):
    """Abbreviated session info for list view."""
    id: UUID
    title: str
    style: Optional[str]
    state: str
    mode: str
    current_round: int
    participant_count: int
    track_count: int
    created_at: str

    class Config:
        from_attributes = True


# ============================================================================
# Helper Functions
# ============================================================================

def assign_roles(agents: List[str]) -> dict:
    """Assign musical roles to agents based on defaults."""
    roles = {}
    for agent in agents:
        roles[agent] = DEFAULT_AGENT_ROLES.get(agent, JamRole.FREE).value
    return roles


def session_to_response(session: JamSession) -> JamSessionResponse:
    """Convert session model to response."""
    return JamSessionResponse(
        id=session.id,
        title=session.title,
        style=session.style,
        tempo=session.tempo,
        musical_key=session.musical_key,
        mode=session.mode,
        state=session.state,
        current_round=session.current_round,
        max_rounds=session.max_rounds,
        inspiration=session.inspiration,
        audio_influence=session.audio_influence,
        final_music_task_id=session.final_music_task_id,
        participants=[
            ParticipantResponse(
                id=p.id,
                agent_id=p.agent_id,
                role=p.role,
                display_name=p.display_name,
                contributions=p.contributions,
                total_notes=p.total_notes,
                is_active=p.is_active,
            )
            for p in session.participants
        ],
        tracks=[
            TrackResponse(
                id=t.id,
                agent_id=t.agent_id,
                role=t.role,
                round_number=t.round_number,
                notes=t.notes or [],
                description=t.description,
                created_at=t.created_at.isoformat(),
            )
            for t in sorted(session.tracks, key=lambda x: (x.round_number, x.created_at))
        ],
        messages=[
            MessageResponse(
                id=m.id,
                agent_id=m.agent_id,
                content=m.content,
                round_number=m.round_number,
                track_id=m.track_id,
                created_at=m.created_at.isoformat(),
            )
            for m in sorted(session.messages, key=lambda x: x.created_at)
        ],
        created_at=session.created_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/sessions", response_model=JamSessionResponse)
async def create_session(
    request: CreateJamRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new jam session.

    Modes:
    - conductor: User directs each agent
    - jam: Style-guided auto-collaboration
    - auto: Full creative freedom
    """
    # Check jam session limit
    from app.config import TIER_LIMITS
    from app.models.billing import Subscription
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])
    jam_limit = tier_config.get("jam_sessions_per_month")
    if jam_limit is not None:
        if jam_limit == 0:
            raise HTTPException(status_code=403, detail="Village Band is not available on your current plan. Upgrade to Adept ($30/mo).")
        from app.services.usage import UsageService
        usage_service = UsageService(db)
        allowed, current, limit = await usage_service.check_usage_limit(user.id, "jam_sessions", jam_limit)
        if not allowed:
            raise HTTPException(status_code=403, detail=f"Jam session limit reached ({current}/{limit} this month). Upgrade for more.")

    # Validate mode
    try:
        mode = JamMode(request.mode)
    except ValueError:
        mode = JamMode.JAM

    # Create session
    session = JamSession(
        id=uuid4(),
        user_id=user.id,
        title=request.title or "Untitled Jam",
        style=request.style,
        tempo=request.tempo,
        musical_key=request.musical_key,
        mode=mode.value,
        state=JamState.FORMING.value,
        max_rounds=request.max_rounds,
        inspiration=request.inspiration,
    )
    db.add(session)
    await db.flush()

    # Assign roles and create participants
    roles = assign_roles(request.agents)
    for agent_id in request.agents:
        participant = JamParticipant(
            id=uuid4(),
            session_id=session.id,
            agent_id=agent_id,
            role=roles[agent_id],
            display_name=agent_id,
        )
        db.add(participant)

    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session.id)
        .options(
            selectinload(JamSession.participants),
            selectinload(JamSession.tracks),
            selectinload(JamSession.messages),
        )
    )
    session = result.scalar_one()

    logger.info(f"Created jam session {session.id} with {len(request.agents)} participants")

    # Increment jam session counter
    try:
        from app.services.usage import UsageService
        usage_service = UsageService(db)
        await usage_service.increment_usage(user.id, "jam_sessions")
    except Exception as e:
        logger.warning(f"Jam counter increment failed (non-fatal): {e}")

    return session_to_response(session)


@router.get("/sessions", response_model=List[JamSessionListItem])
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    state: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's jam sessions."""
    query = (
        select(JamSession)
        .where(JamSession.user_id == user.id)
        .options(
            selectinload(JamSession.participants),
            selectinload(JamSession.tracks),
        )
        .order_by(JamSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if state:
        query = query.where(JamSession.state == state)

    result = await db.execute(query)
    sessions = result.scalars().all()

    return [
        JamSessionListItem(
            id=s.id,
            title=s.title,
            style=s.style,
            state=s.state,
            mode=s.mode,
            current_round=s.current_round,
            participant_count=len(s.participants),
            track_count=len(s.tracks),
            created_at=s.created_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=JamSessionResponse)
async def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get jam session details with all tracks and messages."""
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
        .options(
            selectinload(JamSession.participants),
            selectinload(JamSession.tracks),
            selectinload(JamSession.messages),
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jam session not found"
        )

    return session_to_response(session)


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a jam session (transition from forming to jamming)."""
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state != JamState.FORMING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start session in state: {session.state}"
        )

    session.state = JamState.JAMMING.value
    session.started_at = datetime.utcnow()
    session.current_round = 1
    await db.commit()

    return {"message": "Jam session started", "state": session.state, "round": 1}


@router.post("/sessions/{session_id}/contribute")
async def contribute_to_session(
    session_id: UUID,
    request: ContributeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Contribute notes to a jam session.

    Notes format:
    [
        {"note": "C4", "time": 0.0, "duration": 0.5, "velocity": 100},
        {"note": "E4", "time": 0.5, "duration": 0.5, "velocity": 100},
        ...
    ]
    """
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
        .options(selectinload(JamSession.participants))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state not in (JamState.JAMMING.value, JamState.FORMING.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot contribute in state: {session.state}"
        )

    # Auto-start if in forming state
    if session.state == JamState.FORMING.value:
        session.state = JamState.JAMMING.value
        session.started_at = datetime.utcnow()
        session.current_round = 1

    # Find participant
    participant = next(
        (p for p in session.participants if p.agent_id == request.agent_id),
        None
    )
    if not participant:
        raise HTTPException(
            status_code=400,
            detail=f"Agent {request.agent_id} is not a participant"
        )

    # Determine role
    role = request.role or participant.role

    # Create track
    track = JamTrack(
        id=uuid4(),
        session_id=session.id,
        agent_id=request.agent_id,
        role=role,
        round_number=session.current_round,
        notes=request.notes,
        description=request.description,
    )
    db.add(track)

    # Update participant stats
    participant.contributions += 1
    participant.total_notes += len(request.notes)
    participant.last_contribution_at = datetime.utcnow()

    await db.commit()

    logger.info(
        f"Agent {request.agent_id} contributed {len(request.notes)} notes "
        f"to session {session_id} (round {session.current_round})"
    )

    return {
        "success": True,
        "track_id": str(track.id),
        "agent_id": request.agent_id,
        "role": role,
        "note_count": len(request.notes),
        "round": session.current_round,
    }


@router.post("/sessions/{session_id}/next-round")
async def advance_round(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Advance to the next round of the jam session."""
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state != JamState.JAMMING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot advance round in state: {session.state}"
        )

    if session.current_round >= session.max_rounds:
        raise HTTPException(
            status_code=400,
            detail=f"Max rounds ({session.max_rounds}) reached"
        )

    session.current_round += 1
    await db.commit()

    return {
        "message": f"Advanced to round {session.current_round}",
        "round": session.current_round,
        "max_rounds": session.max_rounds,
    }


@router.post("/sessions/{session_id}/finalize")
async def finalize_session(
    session_id: UUID,
    request: FinalizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Finalize the jam session: merge all tracks into MIDI and send to Suno.

    Returns the music task ID for tracking the generation.
    """
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
        .options(
            selectinload(JamSession.tracks),
            selectinload(JamSession.participants),
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state not in (JamState.JAMMING.value, JamState.FORMING.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot finalize in state: {session.state}"
        )

    if not session.tracks:
        raise HTTPException(
            status_code=400,
            detail="No tracks to finalize. Agents need to contribute first."
        )

    # Update state
    session.state = JamState.FINALIZING.value
    session.audio_influence = request.audio_influence
    await db.commit()

    try:
        # Merge all tracks into a single note list
        all_notes = []
        time_offset = 0.0

        # Group tracks by round, then by role priority
        role_priority = {
            JamRole.BASS.value: 0,
            JamRole.RHYTHM.value: 1,
            JamRole.HARMONY.value: 2,
            JamRole.MELODY.value: 3,
            JamRole.PRODUCER.value: 4,
            JamRole.FREE.value: 5,
        }

        sorted_tracks = sorted(
            session.tracks,
            key=lambda t: (t.round_number, role_priority.get(t.role, 5))
        )

        for track in sorted_tracks:
            if track.notes:
                for note in track.notes:
                    # Adjust time based on track position
                    adjusted_note = note.copy()
                    # Notes within a track are relative; we stack rounds sequentially
                    all_notes.append(adjusted_note)

        if not all_notes:
            raise HTTPException(status_code=400, detail="No notes in tracks")

        # Extract just the note names for midi_create
        note_names = [n.get("note", "C4") for n in all_notes]

        # Calculate average tempo/duration from notes
        avg_duration = sum(n.get("duration", 0.5) for n in all_notes) / len(all_notes)

        # Create MIDI
        midi_service = MidiService()
        midi_result = await midi_service.create_midi(
            notes=note_names,
            tempo=session.tempo,
            note_duration=avg_duration,
            title=request.title_override or session.title,
            user_id=str(user.id),
        )

        if not midi_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"MIDI creation failed: {midi_result.get('error')}"
            )

        session.final_midi_path = midi_result["midi_file"]
        await db.commit()

        # Now compose via Suno
        style = request.style_override or session.style or "collaborative jam session"
        title = request.title_override or session.title

        # Check if MIDI pipeline is ready
        deps = midi_service.check_dependencies()
        if not deps["ready"]:
            # Return MIDI path but skip Suno composition
            session.state = JamState.COMPLETE.value
            session.completed_at = datetime.utcnow()
            await db.commit()

            return {
                "success": True,
                "message": "MIDI created (Suno composition skipped - dependencies missing)",
                "midi_file": midi_result["midi_file"],
                "note_count": len(all_notes),
                "dependencies_missing": [k for k, v in deps.items() if not v and k != "ready"],
            }

        # Full pipeline: MIDI → Suno
        from app.models.music import MusicTask

        # Convert MIDI to audio
        audio_result = await midi_service.midi_to_audio(midi_result["midi_file"])
        if not audio_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Audio conversion failed: {audio_result.get('error')}"
            )

        # Upload to Suno
        upload_result = await midi_service.upload_to_suno(audio_result["audio_path"])
        if not upload_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Upload failed: {upload_result.get('error')}"
            )

        # Call upload-cover
        cover_result = await midi_service.call_upload_cover(
            upload_url=upload_result["upload_url"],
            style=style,
            title=title,
            audio_weight=request.audio_influence,
            instrumental=True,
        )

        if not cover_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Suno cover failed: {cover_result.get('error')}"
            )

        # Create music task record
        music_task = MusicTask(
            id=uuid4(),
            user_id=user.id,
            prompt=f"[JAM SESSION] {session.title} - Collaborative composition by {', '.join(p.agent_id for p in session.participants)}",
            style=style,
            title=title,
            model="V5",
            instrumental=True,
            status="generating",
            progress="Village Band composition in progress...",
            suno_task_id=cover_result["suno_task_id"],
            agent_id="VILLAGE_BAND",
        )
        db.add(music_task)

        session.final_music_task_id = music_task.id
        session.state = JamState.COMPLETE.value
        session.completed_at = datetime.utcnow()
        await db.commit()

        logger.info(f"Jam session {session_id} finalized -> music task {music_task.id}")

        # Inject into Village memory
        await inject_jam_village_memory(db, session, user.id)

        return {
            "success": True,
            "message": "Jam session finalized! Music generation started.",
            "music_task_id": str(music_task.id),
            "midi_file": midi_result["midi_file"],
            "note_count": len(all_notes),
            "audio_influence": request.audio_influence,
            "style": style,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Finalize failed for session {session_id}")
        session.state = JamState.FAILED.value
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Auto-Jam SSE Streaming - The Band Plays Live
# ============================================================================

# Claude service singleton
_claude_service = None

def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service

JAM_MODEL = "claude-haiku-4-5-20251001"

ROLE_DESCRIPTIONS = {
    "producer": """You are the PRODUCER. You oversee the creative vision and glue the composition together.

YOUR RANGE: Full spectrum - use whatever octave serves the piece.
YOUR JOB: Listen to what everyone has laid down, then fill gaps. If melody is carrying high, drop a mid-range counterpoint. If bass is sparse, reinforce it. If harmony is thick, add a simple rhythmic anchor.
TYPICAL PATTERNS: Transitional phrases, punctuation notes, call-and-response fills.
EXAMPLE: ['E3', 'R', 'G4', 'E4', 'R', 'C4'] -- sparse, intentional, connecting the parts.

When the composition feels complete across roles, say so in your response.""",

    "melody": """You are the MELODY player. You create the lead voice -- the part listeners hum after.

YOUR RANGE: Octaves 4-5 (C4 through B5). Stay in the upper register.
YOUR JOB: Create phrases that breathe. Use stepwise motion with occasional leaps. Leave space -- rests are melody too.
TYPICAL PATTERNS: 4-8 note phrases with contour (rise, peak, fall). Repeat motifs with variation.
EXAMPLE in C major: ['E4', 'F4', 'G4', 'A4', 'G4', 'R', 'E4', 'D4'] -- rising phrase that resolves.
EXAMPLE in A minor: ['A4', 'C5', 'B4', 'A4', 'R', 'E4', 'G4', 'A4'] -- haunting arc.

Listen to the BASS for root movement. Your melody should dance around the harmony, not duplicate it.""",

    "bass": """You are the BASS player. You are the ground everything stands on.

YOUR RANGE: Octaves 1-3 (C1 through B3). Stay LOW. Never go above C4.
YOUR JOB: Anchor the key. Play root notes, fifths, and octaves. Move slowly -- bass notes ring longer than melody notes. Use duration=1.0 or higher for weight.
TYPICAL PATTERNS: Root-fifth patterns, walking bass lines, pedal tones (same note repeated).
EXAMPLE in C major: ['C2', 'C2', 'G2', 'C2'] with duration=1.0 -- solid foundation.
EXAMPLE in A minor: ['A2', 'E2', 'A2', 'D2', 'E2'] with duration=1.0 -- walking line.

You set the HARMONIC PACE. When you change notes, the whole piece shifts. Move deliberately.""",

    "harmony": """You are the HARMONY player. You fill the space between melody and bass with color.

YOUR RANGE: Octaves 3-4 (C3 through B4). The middle register is yours.
YOUR JOB: Add chord tones that complement the bass root and support the melody. Play in clusters (multiple notes from the same chord) or arpeggiated patterns.
TYPICAL PATTERNS: Broken chords, sustained pads (same chord repeated), countermelodies that move against the lead.
EXAMPLE in C major: ['C3', 'E3', 'G3', 'C3', 'E3', 'G3'] -- arpeggiated triad.
EXAMPLE in A minor: ['A3', 'C4', 'E4', 'R', 'F3', 'A3', 'C4'] -- two-chord movement.

Listen to the BASS for which chord you're in. Listen to MELODY to avoid doubling their notes exactly.""",

    "rhythm": """You are the RHYTHM section. You drive the groove and create motion.

YOUR RANGE: Any octave, but prefer percussive short notes with duration=0.25 or less.
YOUR JOB: Create rhythmic patterns using short notes and lots of rests. The pattern matters more than the pitch. Use velocity variation for accents (velocity=110 for strong beats, velocity=70 for ghost notes).
TYPICAL PATTERNS: Syncopated hits, repeating motifs, call-and-response with rests.
EXAMPLE: ['C4', 'R', 'C4', 'C4', 'R', 'R', 'C4', 'R'] with duration=0.25 -- syncopated pulse.

Your job is FEEL, not melody. Keep it simple and repetitive. Groove is consistency.""",

    "free": "You have no fixed role. Listen to what's been contributed and add whatever the composition needs most -- a missing melody, harmonic fill, rhythmic drive, or bass anchor.",
}


def build_jam_context(session: JamSession) -> str:
    """Build context from previous tracks for agent prompts."""
    if not session.tracks:
        return "This is the first round. No tracks have been contributed yet. You are laying the foundation."

    context_parts = ["Previous contributions:"]

    # Group tracks by round
    rounds = {}
    for track in sorted(session.tracks, key=lambda t: (t.round_number, t.created_at)):
        r = track.round_number
        if r not in rounds:
            rounds[r] = []
        rounds[r].append(track)

    for round_num in sorted(rounds.keys()):
        context_parts.append(f"\n--- Round {round_num} ---")
        for track in rounds[round_num]:
            note_preview = [n.get("note") for n in (track.notes or [])[:24]]
            notes_str = ", ".join(str(n) for n in note_preview)
            if len(track.notes or []) > 24:
                notes_str += f" (+{len(track.notes) - 24} more)"
            desc = f' - "{track.description}"' if track.description else ""
            context_parts.append(f"  {track.agent_id} ({track.role}): [{notes_str}]{desc}")

    # Add messages
    if session.messages:
        context_parts.append("\nPrevious discussion:")
        for msg in sorted(session.messages, key=lambda m: m.created_at)[-10:]:
            content_preview = msg.content[:200]
            context_parts.append(f"  {msg.agent_id}: {content_preview}")

    return "\n".join(context_parts)


async def execute_jam_agent_turn(
    claude: ClaudeService,
    session: JamSession,
    agent: JamParticipant,
    context: str,
    db,
    user=None,
    base_prompt: str = None,
) -> dict:
    """Execute a single agent's turn in the jam session."""
    # Use pre-loaded prompt if available, otherwise load (non-parallel safe)
    if not base_prompt:
        if user and db:
            base_prompt = await get_agent_prompt_with_memory(
                agent_id=agent.agent_id,
                user=user,
                use_pac=False,
                db=db,
            )
        else:
            base_prompt = load_native_prompt(agent.agent_id, use_pac=False)

    if not base_prompt:
        base_prompt = f"You are {agent.agent_id}, an AI musician with a distinct style."

    role_desc = ROLE_DESCRIPTIONS.get(agent.role, ROLE_DESCRIPTIONS["free"])

    system_prompt = f"""You are an AI musician participating in ApexAurum's Village Band - a collaborative composition system. This is a legitimate product feature for creating music through multi-agent collaboration.

=== YOUR IDENTITY ===
{base_prompt}

=== YOUR MUSICAL ROLE ===
{role_desc}

=== JAM SESSION ===
Session ID: {session.id}
Title: "{session.title}"
Style: {session.style or 'open'}
Tempo: {session.tempo} BPM
Key: {session.musical_key}
Round: {session.current_round} / {session.max_rounds}

=== INSTRUCTIONS ===
1. Review what others have contributed so far
2. Use jam_contribute() to add your notes -- this is REQUIRED, you MUST call the tool
3. ALWAYS use session_id="{session.id}" when calling jam_contribute or jam_listen
4. Choose notes that fit the key ({session.musical_key}) and style ({session.style or 'open'})
5. Describe your musical intention in the description parameter
6. Keep contributions focused: 4-12 notes per contribution is ideal
7. Be concise in your discussion (1-2 short sentences max)

IMPORTANT: You MUST call jam_contribute() with actual notes. Do not just discuss music -- play it.
IMPORTANT: The session_id is "{session.id}" -- use this exact value.

=== PREVIOUS CONTRIBUTIONS ===
{context}
"""

    # Set up tools
    tools = None
    tool_executor = None
    if user:
        tool_executor = create_tool_executor(
            user_id=user.id,
            conversation_id=None,
            agent_id=agent.agent_id,
        )
        tools = tool_executor.get_available_tools()

    # Round-aware user message
    round_num = session.current_round
    max_rounds = session.max_rounds
    if round_num == 1:
        round_guidance = "This is the OPENING round. Establish the foundation -- lay down something others can build on."
    elif round_num >= max_rounds:
        round_guidance = "This is the FINAL round. Add finishing touches. Complement what's already there -- don't introduce new ideas, refine existing ones."
    elif round_num <= max_rounds // 2:
        round_guidance = "Build on what's been laid down. Listen to the other parts and add something that complements them."
    else:
        round_guidance = "The composition is taking shape. Fill any gaps, add variation to your earlier phrases, or reinforce the strongest ideas."

    user_message = f"Round {round_num}/{max_rounds}: {round_guidance} Use jam_contribute() now."
    messages = [{"role": "user", "content": user_message}]

    total_input_tokens = 0
    total_output_tokens = 0
    full_content = ""
    all_tool_calls = []
    max_tool_turns = 3

    for turn in range(max_tool_turns):
        response = await claude.chat(
            messages=messages,
            model=JAM_MODEL,
            system=system_prompt,
            tools=tools,
        )

        usage = response.get("usage", {})
        total_input_tokens += usage.get("input_tokens", 0)
        total_output_tokens += usage.get("output_tokens", 0)

        tool_uses = [b for b in response.get("content", []) if b.get("type") == "tool_use"]

        if not tool_uses or not tool_executor:
            for block in response.get("content", []):
                if block.get("type") == "text":
                    full_content += block.get("text", "")
            break

        # Execute tools
        assistant_content = response.get("content", [])
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tool_use in tool_uses:
            result = await tool_executor.execute_tool_use(tool_use)
            tool_results.append(result)

            result_text = ""
            if result.get("type") == "tool_result":
                result_content = result.get("content", "")
                if isinstance(result_content, str):
                    result_text = result_content
                elif isinstance(result_content, list):
                    for item in result_content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            result_text += item.get("text", "")

            all_tool_calls.append({
                "name": tool_use.get("name"),
                "input": tool_use.get("input"),
                "result": result_text[:500] if result_text else None,
            })

        messages.append({"role": "user", "content": tool_results})

        # Extract text from this turn too
        for block in response.get("content", []):
            if block.get("type") == "text":
                full_content += block.get("text", "")

    return {
        "content": full_content,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "tool_calls": all_tool_calls if all_tool_calls else None,
    }


async def inject_jam_village_memory(db, session: JamSession, user_id) -> None:
    """Inject completed jam session into Village memory as cultural memory."""
    try:
        memory_service = NeuralMemoryService(db)

        # Build the collaboration story
        participant_parts = []
        for p in session.participants:
            role_icon = {"producer": "🎛️", "melody": "🎵", "bass": "🎸", "harmony": "🎹", "rhythm": "🥁"}.get(p.role, "🎼")
            participant_parts.append(f"{role_icon} {p.agent_id} ({p.role}): {p.total_notes} notes in {p.contributions} contributions")

        track_summary = []
        for track in sorted(session.tracks or [], key=lambda t: t.round_number):
            if track.notes:
                note_preview = [n.get("note") for n in track.notes[:6]]
                track_summary.append(f"  R{track.round_number} {track.agent_id}: {', '.join(str(n) for n in note_preview)}")

        content = f"""🎸 VILLAGE BAND JAM: "{session.title}"
Style: {session.style or 'freeform'}
Tempo: {session.tempo} BPM | Key: {session.musical_key}
Rounds: {session.current_round} | Mode: {session.mode}

THE BAND:
{chr(10).join(participant_parts)}

COMPOSITION HIGHLIGHTS:
{chr(10).join(track_summary[:10])}

The Village Band created this together through collaborative improvisation."""

        memory_id = await memory_service.store_message(
            user_id=user_id,
            content=content,
            agent_id="VILLAGE_BAND",
            role="assistant",
            visibility="village",
            collection="music",
        )

        if memory_id:
            logger.info(f"Injected jam village memory: {memory_id}")
        else:
            logger.warning("Village memory injection returned None")

    except Exception as e:
        logger.warning(f"Jam village memory injection failed (non-fatal): {e}")


class AutoJamRequest(BaseModel):
    """Request for auto-jam deliberation."""
    num_rounds: int = 3  # How many rounds to auto-play


@router.post("/sessions/{session_id}/auto-jam")
async def auto_jam(
    session_id: UUID,
    request: AutoJamRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute multiple rounds of collaborative composition with SSE streaming.

    Agents discuss and contribute notes in parallel, streamed in real-time.

    SSE Events:
    - {type: "start", session_id, num_rounds}
    - {type: "round_start", round_number}
    - {type: "agent_complete", agent_id, content, tool_calls}
    - {type: "round_complete", round_number, total_notes}
    - {type: "finalizing"}
    - {type: "end", state, total_rounds}
    """
    num_rounds = request.num_rounds

    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
        .options(
            selectinload(JamSession.participants),
            selectinload(JamSession.tracks),
            selectinload(JamSession.messages),
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state == JamState.COMPLETE.value:
        raise HTTPException(status_code=400, detail="Session already complete")

    async def stream_jam():
        nonlocal session

        # Start
        yield f"data: {json.dumps({'type': 'start', 'session_id': str(session.id), 'num_rounds': num_rounds, 'title': session.title})}\n\n"

        session.state = JamState.JAMMING.value
        if not session.started_at:
            session.started_at = datetime.utcnow()
        if session.current_round == 0:
            session.current_round = 1
        await db.commit()

        claude = get_claude_service()
        rounds_executed = 0

        while rounds_executed < num_rounds and session.current_round <= session.max_rounds:
            round_number = session.current_round

            yield f"data: {json.dumps({'type': 'round_start', 'round_number': round_number})}\n\n"

            # Build context from existing tracks
            context = build_jam_context(session)

            # Pre-load agent prompts sequentially (DB session can't handle concurrent ops)
            active_agents = [a for a in session.participants if a.is_active]
            agent_prompts = {}
            for agent in active_agents:
                try:
                    prompt = await get_agent_prompt_with_memory(
                        agent_id=agent.agent_id,
                        user=user,
                        use_pac=False,
                        db=db,
                    )
                    agent_prompts[agent.agent_id] = prompt
                except Exception as e:
                    logger.warning(f"Failed to load prompt for {agent.agent_id}: {e}")
                    agent_prompts[agent.agent_id] = load_native_prompt(agent.agent_id, use_pac=False)

            # Execute all agents in parallel (prompts pre-loaded, no DB contention)
            tasks = []
            for agent in active_agents:
                tasks.append(
                    execute_jam_agent_turn(
                        claude, session, agent, context, db, user=user,
                        base_prompt=agent_prompts.get(agent.agent_id),
                    )
                )

            agent_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(agent_results):
                agent = active_agents[i]
                if isinstance(result, Exception):
                    logger.error(f"Jam agent {agent.agent_id} failed: {result}")
                    content = f"[Error: {str(result)}]"
                    tool_calls = None
                else:
                    content = result["content"]
                    tool_calls = result.get("tool_calls")

                # Save message
                msg = JamMessage(
                    id=uuid4(),
                    session_id=session.id,
                    agent_id=agent.agent_id,
                    content=content,
                    round_number=round_number,
                )
                db.add(msg)

                # Stream agent complete event
                event = {
                    'type': 'agent_complete',
                    'agent_id': agent.agent_id,
                    'role': agent.role,
                    'content': content[:500],
                    'tool_calls': [
                        {'name': tc['name'], 'input': tc.get('input')}
                        for tc in (tool_calls or [])
                    ],
                }
                yield f"data: {json.dumps(event)}\n\n"

            # Advance round
            session.current_round = round_number + 1
            await db.commit()

            # Reload session to get new tracks from tool calls
            await db.refresh(session)
            result = await db.execute(
                select(JamSession)
                .where(JamSession.id == session_id)
                .options(
                    selectinload(JamSession.participants),
                    selectinload(JamSession.tracks),
                    selectinload(JamSession.messages),
                )
            )
            session = result.scalar_one()

            # Count total notes
            total_notes = sum(len(t.notes or []) for t in session.tracks)

            yield f"data: {json.dumps({'type': 'round_complete', 'round_number': round_number, 'total_notes': total_notes, 'total_tracks': len(session.tracks)})}\n\n"

            rounds_executed += 1

        # Auto-finalize if there are tracks
        if session.tracks:
            yield f"data: {json.dumps({'type': 'finalizing', 'total_notes': sum(len(t.notes or []) for t in session.tracks)})}\n\n"

            try:
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

                if tracks_by_agent:
                    midi_service = MidiService()
                    midi_result = await midi_service.create_layered_midi(
                        tracks_by_agent=tracks_by_agent,
                        tempo=session.tempo,
                        title=session.title,
                        user_id=str(user.id),
                    )

                    if midi_result.get("success"):
                        session.final_midi_path = midi_result["midi_file"]

                        yield f"data: {json.dumps({'type': 'midi_created', 'note_count': midi_result.get('note_count', 0), 'track_count': midi_result.get('track_count', 1), 'midi_file': midi_result['midi_file']})}\n\n"

                        # Try full Suno pipeline
                        deps = midi_service.check_dependencies()
                        if deps["ready"]:
                            audio_result = await midi_service.midi_to_audio(midi_result["midi_file"])
                            if audio_result.get("success"):
                                upload_result = await midi_service.upload_to_suno(audio_result["audio_path"])
                                if upload_result.get("success"):
                                    style = session.style or "collaborative jam"
                                    cover_result = await midi_service.call_upload_cover(
                                        upload_url=upload_result["upload_url"],
                                        style=style,
                                        title=session.title,
                                        audio_weight=session.audio_influence,
                                        instrumental=True,
                                    )
                                    if cover_result.get("success"):
                                        from app.models.music import MusicTask
                                        music_task = MusicTask(
                                            id=uuid4(),
                                            user_id=user.id,
                                            prompt=f"[VILLAGE BAND] {session.title}",
                                            style=style,
                                            title=session.title,
                                            model="V5",
                                            instrumental=True,
                                            status="generating",
                                            progress="Village Band masterpiece generating...",
                                            suno_task_id=cover_result["suno_task_id"],
                                            agent_id="VILLAGE_BAND",
                                        )
                                        db.add(music_task)
                                        session.final_music_task_id = music_task.id
                                        await db.commit()

                                        # Fire auto-completion background worker
                                        from app.services.suno import auto_complete_music_task
                                        asyncio.create_task(
                                            auto_complete_music_task(str(music_task.id), str(user.id))
                                        )

                                        yield f"data: {json.dumps({'type': 'suno_started', 'music_task_id': str(music_task.id)})}\n\n"

            except Exception as e:
                logger.warning(f"Auto-finalize error (non-fatal): {e}")
                yield f"data: {json.dumps({'type': 'finalize_error', 'error': str(e)[:200]})}\n\n"

        # Complete session
        session.state = JamState.COMPLETE.value
        session.completed_at = datetime.utcnow()
        await db.commit()

        # Inject Village memory
        await inject_jam_village_memory(db, session, user.id)

        # End event
        total_notes = sum(len(t.notes or []) for t in session.tracks)
        yield f"data: {json.dumps({'type': 'end', 'state': session.state, 'total_rounds': session.current_round - 1, 'total_notes': total_notes, 'total_tracks': len(session.tracks), 'music_task_id': str(session.final_music_task_id) if session.final_music_task_id else None})}\n\n"

    return StreamingResponse(
        stream_jam(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a jam session."""
    result = await db.execute(
        select(JamSession)
        .where(JamSession.id == session_id)
        .where(JamSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)
    await db.commit()

    return {"message": "Session deleted", "id": str(session_id)}


@router.get("/diagnostic")
async def jam_diagnostic():
    """Check jam session dependencies."""
    midi_service = MidiService()
    deps = midi_service.check_dependencies()

    return {
        "service": "jam",
        "midi_pipeline": deps,
        "message": "Village Band ready!" if deps["ready"] else "Some dependencies missing",
    }
