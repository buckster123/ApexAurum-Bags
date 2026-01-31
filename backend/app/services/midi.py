"""
MIDI Composition Service - The Athanor's Compositional Hands

Provides MIDI creation and conversion for the music_compose pipeline.
Enables agents to compose note-by-note, then transform via Suno.

Pipeline:
1. midi_create() - Build MIDI from notes
2. midi_to_audio() - FluidSynth → MP3
3. upload_to_suno() - Base64 upload to Suno
4. upload_cover() - Transform with Suno's cover API
"""

import logging
import asyncio
import base64
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

import aiohttp

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Suno API endpoints
SUNO_API_BASE = "https://api.sunoapi.org/api/v1"
SUNO_FILE_UPLOAD_BASE = "https://sunoapiorg.redpandaai.co/api"

# MIDI storage path (within Vault)
MIDI_FOLDER = Path(settings.vault_path) / "midi"

# Soundfont paths (in order of preference)
SOUNDFONT_PATHS = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
]

# Note name to MIDI number mapping
NOTE_MAP = {
    'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11
}


def _find_soundfont() -> Optional[str]:
    """Find an available soundfont file."""
    for sf_path in SOUNDFONT_PATHS:
        if Path(sf_path).exists():
            return sf_path
    return None


def _parse_note(note_str: str) -> int:
    """
    Parse note string to MIDI number.

    Supports:
    - 'C4', 'F#3', 'Bb5' - Note name + accidental + octave
    - '60' - Direct MIDI number

    Args:
        note_str: Note string to parse

    Returns:
        MIDI note number (0-127)
    """
    note_str = note_str.strip()

    # If it's already a number, return it
    if note_str.isdigit():
        return int(note_str)

    # Parse note name
    note_str = note_str.upper()
    base_note = note_str[0]
    if base_note not in NOTE_MAP:
        raise ValueError(f"Invalid note: {note_str}")

    midi_num = NOTE_MAP[base_note]
    idx = 1

    # Check for sharp/flat
    if len(note_str) > idx:
        if note_str[idx] == '#':
            midi_num += 1
            idx += 1
        elif note_str[idx] == 'B':
            midi_num -= 1
            idx += 1

    # Get octave (default to 4 if not specified)
    if idx < len(note_str):
        try:
            octave = int(note_str[idx:])
        except ValueError:
            octave = 4
    else:
        octave = 4

    # MIDI note number: C4 = 60
    return midi_num + (octave + 1) * 12


class MidiService:
    """
    MIDI composition service for creating and converting MIDI files.
    """

    def __init__(self):
        """Initialize MIDI service."""
        # Ensure MIDI folder exists
        MIDI_FOLDER.mkdir(parents=True, exist_ok=True)

    async def create_midi(
        self,
        notes: List[Union[int, str]],
        tempo: int = 120,
        note_duration: float = 0.5,
        title: str = "composition",
        velocity: int = 100,
        rest_between: float = 0.0,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a MIDI file from a list of notes.

        Args:
            notes: List of notes - MIDI numbers or note names ('C4', 'F#3')
                   Use 0 or 'R' for rests
            tempo: Beats per minute
            note_duration: Duration of each note in beats (0.5 = eighth note)
            title: Filename for the MIDI file
            velocity: Note loudness (0-127)
            rest_between: Gap between notes in beats
            user_id: Optional user ID for path organization

        Returns:
            Dict with midi_file path and composition details
        """
        try:
            from midiutil import MIDIFile
        except ImportError:
            return {
                "success": False,
                "error": "midiutil not installed. Add to requirements.txt."
            }

        try:
            # Parse notes
            parsed_notes = []
            for note in notes:
                if note == 0 or (isinstance(note, str) and note.upper() == 'R'):
                    parsed_notes.append(None)  # Rest
                elif isinstance(note, int):
                    parsed_notes.append(note)
                elif isinstance(note, str):
                    parsed_notes.append(_parse_note(note))
                else:
                    return {"success": False, "error": f"Invalid note format: {note}"}

            # Create MIDI file
            midi = MIDIFile(1)  # Single track
            track = 0
            channel = 0
            current_time = 0

            midi.addTempo(track, 0, tempo)

            # Add notes
            note_count = 0
            for note in parsed_notes:
                if note is not None:
                    midi.addNote(track, channel, note, current_time, note_duration, velocity)
                    note_count += 1
                current_time += note_duration + rest_between

            # Generate filename
            safe_title = re.sub(r'[^\w\-]', '_', title)
            timestamp = int(time.time())
            filename = f"{safe_title}_{timestamp}.mid"

            # Determine output path
            if user_id:
                midi_path = MIDI_FOLDER / str(user_id) / filename
                midi_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                midi_path = MIDI_FOLDER / filename

            # Write file
            with open(midi_path, "wb") as f:
                midi.writeFile(f)

            total_duration = current_time * (60 / tempo)  # Beats to seconds

            logger.info(f"Created MIDI: {midi_path} ({note_count} notes, {total_duration:.1f}s)")

            return {
                "success": True,
                "midi_file": str(midi_path),
                "title": title,
                "note_count": note_count,
                "tempo": tempo,
                "duration_seconds": round(total_duration, 2),
                "duration_beats": round(current_time, 2),
            }

        except Exception as e:
            logger.exception("MIDI creation failed")
            return {"success": False, "error": str(e)}

    async def create_layered_midi(
        self,
        tracks_by_agent: Dict[str, List[Dict[str, Any]]],
        tempo: int = 120,
        title: str = "composition",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a multi-track MIDI file with layered parts.

        Each agent gets its own MIDI track, so all parts play simultaneously.
        Used by Village Band jam sessions.

        Args:
            tracks_by_agent: {agent_id: [list of track objects]}
                Each track object has a 'notes' list of note dicts:
                  {"note": "C4", "duration": 0.5, "velocity": 100, "time": 0.0}
                Tracks from the same agent in the same round play sequentially.
                Tracks from different rounds are offset by previous round durations.
            tempo: Beats per minute
            title: Filename for the MIDI file
            user_id: Optional user ID for path organization

        Returns:
            Dict with midi_file path and composition details
        """
        try:
            from midiutil import MIDIFile
        except ImportError:
            return {
                "success": False,
                "error": "midiutil not installed. Add to requirements.txt."
            }

        try:
            agent_ids = list(tracks_by_agent.keys())
            num_tracks = max(len(agent_ids), 1)
            midi = MIDIFile(num_tracks)
            midi.addTempo(0, 0, tempo)

            total_note_count = 0

            for track_idx, agent_id in enumerate(agent_ids):
                channel = track_idx % 15  # MIDI channels 0-15 (skip 9=drums)
                if channel >= 9:
                    channel += 1  # Skip drum channel

                agent_tracks = tracks_by_agent[agent_id]

                # Group this agent's tracks by round for sequential offset
                rounds = {}
                for t in agent_tracks:
                    r = t.get("round_number", 1)
                    if r not in rounds:
                        rounds[r] = []
                    rounds[r].append(t)

                round_offset = 0.0
                for round_num in sorted(rounds.keys()):
                    round_max_dur = 0.0
                    for track in rounds[round_num]:
                        track_time = 0.0
                        for note_obj in (track.get("notes") or []):
                            note_name = str(note_obj.get("note", "C4"))
                            dur = float(note_obj.get("duration", 0.5))
                            vel = int(note_obj.get("velocity", 100))

                            if note_name.upper() not in ("R", "0"):
                                try:
                                    midi_num = _parse_note(note_name)
                                    midi.addNote(
                                        track_idx, channel, midi_num,
                                        round_offset + track_time, dur, vel
                                    )
                                    total_note_count += 1
                                except (ValueError, IndexError):
                                    pass  # Skip unparseable notes
                            track_time += dur
                        round_max_dur = max(round_max_dur, track_time)
                    round_offset += round_max_dur

            # Generate filename
            safe_title = re.sub(r'[^\w\-]', '_', title)
            timestamp = int(time.time())
            filename = f"{safe_title}_{timestamp}.mid"

            if user_id:
                midi_path = MIDI_FOLDER / str(user_id) / filename
                midi_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                midi_path = MIDI_FOLDER / filename

            with open(midi_path, "wb") as f:
                midi.writeFile(f)

            total_duration = round_offset * (60 / tempo)

            logger.info(
                f"Created layered MIDI: {midi_path} "
                f"({num_tracks} tracks, {total_note_count} notes, {total_duration:.1f}s)"
            )

            return {
                "success": True,
                "midi_file": str(midi_path),
                "title": title,
                "note_count": total_note_count,
                "track_count": num_tracks,
                "tempo": tempo,
                "duration_seconds": round(total_duration, 2),
            }

        except Exception as e:
            logger.exception("Layered MIDI creation failed")
            return {"success": False, "error": str(e)}

    async def midi_to_audio(
        self,
        midi_path: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convert MIDI file to MP3 audio using FluidSynth.

        Args:
            midi_path: Path to the MIDI file
            output_path: Optional output path. If None, uses midi_path with .mp3

        Returns:
            Dict with success status and audio_path or error
        """
        try:
            # Check midi2audio availability
            try:
                from midi2audio import FluidSynth
            except ImportError:
                return {
                    "success": False,
                    "error": "midi2audio not installed. Add to requirements.txt."
                }

            # Find soundfont
            soundfont = _find_soundfont()
            if not soundfont:
                return {
                    "success": False,
                    "error": "No soundfont found. Install fluid-soundfont-gm package."
                }

            # Check MIDI file exists
            midi_file = Path(midi_path)
            if not midi_file.exists():
                return {"success": False, "error": f"MIDI file not found: {midi_path}"}

            # Generate output paths
            if output_path:
                mp3_path = Path(output_path)
            else:
                mp3_path = midi_file.with_suffix('.mp3')
            wav_path = mp3_path.with_suffix('.wav')

            # Convert MIDI to WAV (run in thread pool to avoid blocking)
            logger.info(f"Converting MIDI to WAV: {midi_path} -> {wav_path}")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: FluidSynth(soundfont).midi_to_audio(str(midi_path), str(wav_path))
            )

            if not wav_path.exists():
                return {"success": False, "error": "FluidSynth failed to create WAV file"}

            # Convert WAV to MP3
            logger.info(f"Converting WAV to MP3: {wav_path} -> {mp3_path}")

            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(mp3_path)],
                    capture_output=True, text=True
                )
            )

            if result.returncode != 0:
                return {"success": False, "error": f"FFmpeg failed: {result.stderr[:200]}"}

            # Clean up WAV
            try:
                wav_path.unlink()
            except Exception:
                pass

            file_size = mp3_path.stat().st_size
            logger.info(f"MIDI->Audio complete: {mp3_path} ({file_size} bytes)")

            return {
                "success": True,
                "audio_path": str(mp3_path),
                "size_bytes": file_size
            }

        except Exception as e:
            logger.exception("MIDI to audio conversion failed")
            return {"success": False, "error": str(e)}

    async def upload_to_suno(self, audio_path: str) -> Dict[str, Any]:
        """
        Upload an audio file to Suno and get the uploadUrl for use in upload-cover.

        Args:
            audio_path: Path to the audio file (MP3 or WAV)

        Returns:
            Dict with success status and upload_url or error
        """
        api_key = getattr(settings, 'suno_api_key', None)
        if not api_key:
            return {"success": False, "error": "SUNO_API_KEY not configured"}

        audio_file = Path(audio_path)
        if not audio_file.exists():
            return {"success": False, "error": f"Audio file not found: {audio_path}"}

        try:
            # Read and encode file as base64
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')

            # Determine MIME type
            suffix = audio_file.suffix.lower()
            mime_types = {
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.m4a': 'audio/mp4',
                '.ogg': 'audio/ogg'
            }
            mime_type = mime_types.get(suffix, 'audio/mpeg')

            # Upload via base64 endpoint
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "base64Data": f"data:{mime_type};base64,{audio_base64}",
                "uploadPath": "music_compose",
                "fileName": audio_file.name
            }

            logger.info(f"Uploading audio to Suno ({len(audio_data)} bytes)...")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SUNO_FILE_UPLOAD_BASE}/file-base64-upload",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        return {
                            "success": False,
                            "error": f"Upload failed: HTTP {response.status}: {text[:200]}"
                        }

                    result = await response.json()

                    if result.get("code") != 200:
                        return {
                            "success": False,
                            "error": f"Upload API error: {result.get('msg', 'Unknown error')}"
                        }

                    # Try both possible field names for the URL
                    data = result.get("data", {})
                    upload_url = data.get("downloadUrl") or data.get("fileUrl") or data.get("url")

                    if not upload_url:
                        return {
                            "success": False,
                            "error": f"No URL in upload response. Got keys: {list(data.keys())}"
                        }

                    logger.info(f"Audio uploaded: {upload_url[:50]}...")
                    return {
                        "success": True,
                        "upload_url": upload_url,
                        "file_size": len(audio_data)
                    }

        except Exception as e:
            logger.exception("Audio upload failed")
            return {"success": False, "error": str(e)}

    async def call_upload_cover(
        self,
        upload_url: str,
        style: str,
        title: str,
        prompt: str = "",
        instrumental: bool = True,
        audio_weight: float = 0.5,
        style_weight: float = 0.5,
        weirdness: float = 0.3,
        model: str = "V5",
        vocal_gender: str = ""
    ) -> Dict[str, Any]:
        """
        Call Suno's upload-cover endpoint to transform reference audio.

        Args:
            upload_url: URL of the uploaded reference audio
            style: Style tags for the output
            title: Track title
            prompt: Additional lyrics/description
            instrumental: Whether to generate instrumental only
            audio_weight: How much reference affects output (0.0-1.0)
            style_weight: Weight of style guidance (0.0-1.0)
            weirdness: Creative deviation (0.0-1.0)
            model: Suno model version
            vocal_gender: 'm' or 'f' for vocals (if not instrumental)

        Returns:
            Dict with suno_task_id or error
        """
        api_key = getattr(settings, 'suno_api_key', None)
        if not api_key:
            return {"success": False, "error": "SUNO_API_KEY not configured"}

        # Clamp weights to valid range
        audio_weight = max(0.0, min(1.0, audio_weight))
        style_weight = max(0.0, min(1.0, style_weight))
        weirdness = max(0.0, min(1.0, weirdness))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "uploadUrl": upload_url,
            "customMode": True,
            "instrumental": instrumental,
            "model": model,
            "style": style[:1000],
            "title": title[:100],
            "audioWeight": round(audio_weight, 2),
            "styleWeight": round(style_weight, 2),
            "weirdnessConstraint": round(weirdness, 2),
            "callBackUrl": "https://example.com/suno-callback"  # Required but we poll
        }

        if prompt:
            payload["prompt"] = prompt[:5000]

        if not instrumental and vocal_gender in ('m', 'f'):
            payload["vocalGender"] = vocal_gender

        logger.info(f"Calling upload-cover: style='{style[:30]}...', audio_weight={audio_weight}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SUNO_API_BASE}/generate/upload-cover",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        return {
                            "success": False,
                            "error": f"API error: HTTP {response.status}: {text[:200]}"
                        }

                    result = await response.json()

                    if result.get("code") != 200:
                        return {
                            "success": False,
                            "error": f"Suno error: {result.get('msg', 'Unknown error')}"
                        }

                    task_id = result.get("data", {}).get("taskId")
                    if not task_id:
                        return {"success": False, "error": "No taskId in response"}

                    logger.info(f"Upload-cover task created: {task_id}")
                    return {
                        "success": True,
                        "suno_task_id": task_id,
                        "audio_weight": audio_weight,
                        "style_weight": style_weight
                    }

        except Exception as e:
            logger.exception("Upload-cover call failed")
            return {"success": False, "error": str(e)}

    def check_dependencies(self) -> Dict[str, Any]:
        """
        Check if all MIDI pipeline dependencies are available.

        Returns:
            Dict with dependency status for each component
        """
        results = {
            "midiutil": False,
            "midi2audio": False,
            "fluidsynth": False,
            "soundfont": None,
            "ffmpeg": False,
            "ready": False
        }

        # Check midiutil
        try:
            from midiutil import MIDIFile
            results["midiutil"] = True
        except ImportError:
            pass

        # Check midi2audio
        try:
            from midi2audio import FluidSynth
            results["midi2audio"] = True
        except ImportError:
            pass

        # Check fluidsynth binary
        try:
            result = subprocess.run(
                ["fluidsynth", "--version"],
                capture_output=True, text=True
            )
            results["fluidsynth"] = result.returncode == 0
        except FileNotFoundError:
            pass

        # Check soundfont
        results["soundfont"] = _find_soundfont()

        # Check ffmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True
            )
            results["ffmpeg"] = result.returncode == 0
        except FileNotFoundError:
            pass

        # Overall ready check
        results["ready"] = all([
            results["midiutil"],
            results["midi2audio"],
            results["fluidsynth"],
            results["soundfont"],
            results["ffmpeg"]
        ])

        return results
