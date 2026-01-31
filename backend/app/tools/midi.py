"""
Tier 13: MIDI Composition Tools - The Compositional Hands

MIDI creation and composition pipeline for granular music control.

Tools:
- midi_create: Create MIDI files from note arrays
- music_compose: MIDI → Suno composition pipeline

"From notes to neural symphonies"
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory

logger = logging.getLogger(__name__)


# =============================================================================
# MIDI CREATE
# =============================================================================

class MidiCreateTool(BaseTool):
    """Create MIDI files from note arrays."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="midi_create",
            description="""Create a MIDI file from a list of notes.

Use to compose melodies, arpeggios, or chord progressions that can then be
transformed into AI music via music_compose().

Notes can be:
- MIDI numbers: 60 (C4), 64 (E4), 67 (G4)
- Note names: 'C4', 'E4', 'G4', 'F#3', 'Bb5'
- Rests: 0 or 'R'

Example: Create C major arpeggio
>>> midi_create(notes=['C4', 'E4', 'G4', 'C5'], tempo=120, title='c_major')

The output MIDI file path can be passed to music_compose() for AI transformation.""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "notes": {
                        "type": "array",
                        "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                        "description": "List of notes: MIDI numbers (60) or names ('C4'). Use 0 or 'R' for rests.",
                    },
                    "tempo": {
                        "type": "integer",
                        "description": "Beats per minute",
                        "default": 120,
                    },
                    "note_duration": {
                        "type": "number",
                        "description": "Duration per note in beats (0.5 = eighth, 1.0 = quarter)",
                        "default": 0.5,
                    },
                    "title": {
                        "type": "string",
                        "description": "Filename for the MIDI file",
                        "default": "composition",
                    },
                    "velocity": {
                        "type": "integer",
                        "description": "Note loudness (0-127)",
                        "default": 100,
                    },
                    "rest_between": {
                        "type": "number",
                        "description": "Gap between notes in beats",
                        "default": 0.0,
                    },
                },
                "required": ["notes"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        notes = params.get("notes", [])
        if not notes:
            return ToolResult(success=False, error="Notes array is required")

        tempo = params.get("tempo", 120)
        note_duration = params.get("note_duration", 0.5)
        title = params.get("title", "composition")
        velocity = params.get("velocity", 100)
        rest_between = params.get("rest_between", 0.0)

        try:
            from app.services.midi import MidiService

            service = MidiService()

            result = await service.create_midi(
                notes=notes,
                tempo=tempo,
                note_duration=note_duration,
                title=title,
                velocity=velocity,
                rest_between=rest_between,
                user_id=context.user_id,
            )

            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error"))

            return ToolResult(
                success=True,
                result={
                    "midi_file": result["midi_file"],
                    "title": result["title"],
                    "note_count": result["note_count"],
                    "tempo": result["tempo"],
                    "duration_seconds": result["duration_seconds"],
                    "duration_beats": result["duration_beats"],
                    "message": f"MIDI created: {result['midi_file']}. Use with music_compose(midi_file='{result['midi_file']}', ...)",
                },
            )

        except Exception as e:
            logger.exception("MIDI create error")
            return ToolResult(success=False, error=f"MIDI creation failed: {str(e)}")


# =============================================================================
# MUSIC COMPOSE
# =============================================================================

class MusicComposeTool(BaseTool):
    """Generate music using MIDI as compositional reference."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="music_compose",
            description="""Generate AI music using a MIDI file as compositional reference.

The MIDI → Suno pipeline:
1. Your MIDI file (melody, chords, rhythm) is converted to audio
2. Uploaded to Suno as reference
3. Suno generates AI music influenced by your composition

The audio_influence parameter controls how much Suno follows your MIDI:
- 0.2-0.4: Light reference, Suno interprets freely
- 0.5-0.7: Balanced blend of your composition + Suno style
- 0.8-1.0: Suno closely follows your composition

Use for precise compositional control over AI music output.""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "midi_file": {
                        "type": "string",
                        "description": "Path to MIDI file (from midi_create)",
                    },
                    "style": {
                        "type": "string",
                        "description": "Style tags (e.g., 'dark electronic ambient', 'jazz piano')",
                    },
                    "title": {
                        "type": "string",
                        "description": "Track title",
                    },
                    "audio_influence": {
                        "type": "number",
                        "description": "How much MIDI affects output (0.0-1.0). Low=free, High=follow",
                        "default": 0.5,
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Additional description (becomes lyrics if not instrumental)",
                        "default": "",
                    },
                    "instrumental": {
                        "type": "boolean",
                        "description": "True for instrumental, False for vocals",
                        "default": True,
                    },
                    "style_weight": {
                        "type": "number",
                        "description": "How strongly to apply style tags (0.0-1.0)",
                        "default": 0.5,
                    },
                    "weirdness": {
                        "type": "number",
                        "description": "Creative deviation factor (0.0-1.0)",
                        "default": 0.3,
                    },
                    "model": {
                        "type": "string",
                        "enum": ["V3_5", "V4", "V4_5", "V5"],
                        "description": "Suno model version",
                        "default": "V5",
                    },
                },
                "required": ["midi_file", "style", "title"],
            },
            requires_auth=True,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        if not context.user_id:
            return ToolResult(success=False, error="Authentication required")

        midi_file = params.get("midi_file", "")
        style = params.get("style", "")
        title = params.get("title", "")

        if not midi_file:
            return ToolResult(success=False, error="midi_file is required")
        if not style:
            return ToolResult(success=False, error="style is required")
        if not title:
            return ToolResult(success=False, error="title is required")

        audio_influence = params.get("audio_influence", 0.5)
        prompt = params.get("prompt", "")
        instrumental = params.get("instrumental", True)
        style_weight = params.get("style_weight", 0.5)
        weirdness = params.get("weirdness", 0.3)
        model = params.get("model", "V5")

        try:
            from pathlib import Path
            from app.services.midi import MidiService
            from app.models.music import MusicTask
            from app.database import async_session
            from app.services.suno import SunoService

            # Check MIDI file exists
            midi_path = Path(midi_file)
            if not midi_path.exists():
                return ToolResult(success=False, error=f"MIDI file not found: {midi_file}")

            midi_service = MidiService()

            # Check dependencies
            deps = midi_service.check_dependencies()
            if not deps["ready"]:
                missing = [k for k, v in deps.items() if not v and k != "ready"]
                return ToolResult(
                    success=False,
                    error=f"MIDI pipeline dependencies missing: {', '.join(missing)}"
                )

            # Step 1: Convert MIDI to MP3
            logger.info("Step 1: Converting MIDI to audio...")
            temp_mp3 = midi_path.with_suffix('.mp3')
            convert_result = await midi_service.midi_to_audio(str(midi_path), str(temp_mp3))

            if not convert_result.get("success"):
                return ToolResult(
                    success=False,
                    error=f"MIDI conversion failed: {convert_result.get('error')}"
                )

            # Step 2: Upload to Suno
            logger.info("Step 2: Uploading reference audio to Suno...")
            upload_result = await midi_service.upload_to_suno(convert_result["audio_path"])

            if not upload_result.get("success"):
                # Clean up temp file
                try:
                    Path(convert_result["audio_path"]).unlink()
                except Exception:
                    pass
                return ToolResult(
                    success=False,
                    error=f"Upload failed: {upload_result.get('error')}"
                )

            # Step 3: Call upload-cover
            logger.info("Step 3: Calling Suno upload-cover API...")
            cover_result = await midi_service.call_upload_cover(
                upload_url=upload_result["upload_url"],
                style=style,
                title=title,
                prompt=prompt,
                instrumental=instrumental,
                audio_weight=audio_influence,
                style_weight=style_weight,
                weirdness=weirdness,
                model=model,
            )

            if not cover_result.get("success"):
                return ToolResult(
                    success=False,
                    error=f"Upload-cover failed: {cover_result.get('error')}"
                )

            # Clean up temp reference file
            try:
                Path(convert_result["audio_path"]).unlink()
            except Exception:
                pass

            # Step 4: Create database record and start polling
            suno_task_id = cover_result["suno_task_id"]

            async with async_session() as db:
                user_uuid = UUID(context.user_id) if isinstance(context.user_id, str) else context.user_id

                task = MusicTask(
                    id=uuid4(),
                    user_id=user_uuid,
                    prompt=f"[COMPOSED] {prompt}" if prompt else f"[COMPOSED] {style}",
                    style=style,
                    title=title,
                    model=model,
                    instrumental=instrumental,
                    status="generating",
                    progress=f"Composing with audio_influence={audio_influence:.2f}...",
                    suno_task_id=suno_task_id,
                    agent_id=context.agent_id,
                )
                db.add(task)
                await db.commit()

                return ToolResult(
                    success=True,
                    result={
                        "task_id": str(task.id),
                        "suno_task_id": suno_task_id,
                        "status": "generating",
                        "title": title,
                        "audio_influence": audio_influence,
                        "style": style,
                        "model": model,
                        "message": f"Composition started! MIDI transformed with audio_influence={audio_influence}. Poll with music_status('{task.id}'). Takes 2-4 minutes.",
                    },
                )

        except Exception as e:
            logger.exception("Music compose error")
            return ToolResult(success=False, error=f"Composition failed: {str(e)}")


# =============================================================================
# MIDI DIAGNOSTIC
# =============================================================================

class MidiDiagnosticTool(BaseTool):
    """Check MIDI pipeline dependencies."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="midi_diagnostic",
            description="""Check if all MIDI composition pipeline dependencies are available.

Reports status of: midiutil, midi2audio, fluidsynth, soundfont, ffmpeg.
All must be available for music_compose() to work.""",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            requires_auth=False,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            from app.services.midi import MidiService

            service = MidiService()
            deps = service.check_dependencies()

            return ToolResult(
                success=True,
                result={
                    "pipeline_ready": deps["ready"],
                    "dependencies": {
                        "midiutil": "OK" if deps["midiutil"] else "MISSING - pip install midiutil",
                        "midi2audio": "OK" if deps["midi2audio"] else "MISSING - pip install midi2audio",
                        "fluidsynth": "OK" if deps["fluidsynth"] else "MISSING - apt install fluidsynth",
                        "soundfont": deps["soundfont"] or "MISSING - apt install fluid-soundfont-gm",
                        "ffmpeg": "OK" if deps["ffmpeg"] else "MISSING - apt install ffmpeg",
                    },
                    "message": "MIDI pipeline ready!" if deps["ready"] else "Some dependencies missing",
                },
            )

        except Exception as e:
            logger.exception("MIDI diagnostic error")
            return ToolResult(success=False, error=f"Diagnostic failed: {str(e)}")


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(MidiCreateTool())
registry.register(MusicComposeTool())
registry.register(MidiDiagnosticTool())
