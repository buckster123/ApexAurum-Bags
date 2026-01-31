"""
Tier 10: Suno Compiler Tools - The Athanor's Tongue

Advanced prompt compilation for Suno using:
- Emotional cartography
- Symbol injection (kaomoji, math symbols)
- Bark/Chirp manipulation techniques
- Unhinged seed generation

"The tongue that speaks to the music"
"""

import logging
from typing import Optional

from . import registry
from .base import BaseTool, ToolSchema, ToolResult, ToolContext, ToolCategory
from app.services.suno_compiler import compile_prompt, EMOTIONAL_CARTOGRAPHY

logger = logging.getLogger(__name__)


# =============================================================================
# SUNO COMPILE TOOL
# =============================================================================

class SunoCompileTool(BaseTool):
    """Compile creative intent into optimized Suno prompts."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="suno_compile",
            description="""Compile high-level creative intent into an optimized Suno prompt.

Uses emotional cartography, symbol injection (kaomoji/math symbols), and Bark/Chirp
manipulation techniques to unlock Suno's full creative potential.

The compiler transforms simple intent like "mystical bell chime" into rich prompts
with BPM, tuning, emotional percentages, and symbolic structures.

WORKFLOW:
1. Call suno_compile with your creative intent
2. Use the returned prompt/style/title with music_generate

MOODS: mystical, joyful, triumphant, peaceful, energetic, hopeful, playful,
       contemplative, mysterious, ethereal, industrial, digital, melancholic,
       tense, dark, chaotic, ominous, error

PURPOSES: sfx (5-30s), ambient (1-4min), loop (15-60s), song (2-8min), jingle (15-45s)""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What you want to create (e.g., 'mystical bell chime', 'epic battle anthem', 'glitchy error sound')"
                    },
                    "mood": {
                        "type": "string",
                        "description": "Emotional mood: mystical, joyful, dark, peaceful, energetic, ethereal, contemplative, triumphant, etc.",
                        "default": "mystical"
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Generation purpose: sfx, ambient, loop, song, jingle",
                        "default": "song"
                    },
                    "genre": {
                        "type": "string",
                        "description": "Base genre (e.g., 'ambient chime', 'electronic dubstep', 'orchestral epic')",
                        "default": ""
                    },
                    "weirdness": {
                        "type": "integer",
                        "description": "Experimentation level 0-100. Higher = more chaotic/experimental",
                        "default": 50
                    },
                    "instrumental": {
                        "type": "boolean",
                        "description": "True for instrumental, False for vocals",
                        "default": True
                    }
                },
                "required": ["intent"]
            },
            requires_auth=False,  # Compilation is pure transformation, no external API
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        intent = params.get("intent", "").strip()
        if not intent:
            return ToolResult(success=False, error="Intent is required")

        mood = params.get("mood", "mystical")
        purpose = params.get("purpose", "song")
        genre = params.get("genre", "")
        weirdness = params.get("weirdness", 50)
        instrumental = params.get("instrumental", True)

        try:
            compiled = compile_prompt(
                intent=intent,
                mood=mood,
                purpose=purpose,
                genre=genre,
                weirdness=weirdness,
                instrumental=instrumental,
            )

            # Get music_generate args
            gen_args = compiled.to_music_generate_args()

            result = {
                "compiled": {
                    "prompt": gen_args["prompt"],
                    "style": gen_args["style"],
                    "title": gen_args["title"],
                    "model": gen_args["model"],
                    "instrumental": gen_args["instrumental"],
                },
                "metadata": {
                    "mood": compiled.mood,
                    "purpose": compiled.purpose,
                    "weirdness_pct": compiled.weirdness_pct,
                    "style_pct": compiled.style_pct,
                },
                "unhinged_seed": compiled.unhinged_seed,
                "usage_hint": "Use the 'compiled' values with music_generate tool",
            }

            # Add emotional cartography info
            if mood in EMOTIONAL_CARTOGRAPHY:
                ec = EMOTIONAL_CARTOGRAPHY[mood]
                result["emotional_cartography"] = {
                    "primary": ec["primary"],
                    "primary_pct": ec["primary_pct"],
                    "secondary": ec["secondary"],
                    "secondary_pct": ec["secondary_pct"],
                }

            logger.info(f"Compiled Suno prompt: intent='{intent[:50]}', mood={mood}, purpose={purpose}")

            return ToolResult(success=True, result=result)

        except Exception as e:
            logger.exception("Suno compile failed")
            return ToolResult(success=False, error=str(e))


# =============================================================================
# SUNO MOODS TOOL
# =============================================================================

class SunoMoodsTool(BaseTool):
    """List available moods with their emotional cartography."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="suno_moods",
            description="""List all available moods for the Suno compiler.

Returns each mood with its emotional cartography mapping:
- Primary emotion and percentage
- Secondary emotion and percentage

Use this to discover available moods before calling suno_compile.""",
            category=ToolCategory.CREATIVE,
            input_schema={
                "type": "object",
                "properties": {},
            },
            requires_auth=False,
        )

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        moods = {}
        for mood_name, ec in EMOTIONAL_CARTOGRAPHY.items():
            moods[mood_name] = {
                "primary": f"{ec['primary']} ({ec['primary_pct']}%)",
                "secondary": f"{ec['secondary']} ({ec['secondary_pct']}%)",
            }

        return ToolResult(
            success=True,
            result={
                "moods": moods,
                "count": len(moods),
                "categories": {
                    "positive": ["mystical", "joyful", "triumphant", "peaceful", "energetic", "hopeful", "playful"],
                    "neutral": ["contemplative", "mysterious", "ethereal", "industrial", "digital"],
                    "negative": ["melancholic", "tense", "dark", "chaotic", "ominous", "error"],
                }
            }
        )


# =============================================================================
# REGISTER TOOLS
# =============================================================================

registry.register(SunoCompileTool())
registry.register(SunoMoodsTool())
