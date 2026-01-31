"""
Suno Prompt Compiler - Transform intent into optimized Suno prompts

The Athanor's tongue - translating creative vision into Suno's native language.

Based on the comprehensive Suno Prompt Generation System:
- Intent parsing and template selection
- Mood → emotional cartography mapping
- Symbol/kaomoji injection for Bark/Chirp manipulation
- Weirdness/Style balance optimization
- Unhinged seed generation for creativity boost

Architecture:
    User Intent → Intent Parser → Template Selector → Parameter Injector
              → Symbol Compiler → Unhinged Seed Generator → Final Prompt
"""

import random
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class Purpose(Enum):
    """Music generation purpose - affects structure and length"""
    SFX = "sfx"              # Short sound effect (5-30s)
    AMBIENT = "ambient"       # Background/atmosphere (1-4min)
    LOOP = "loop"            # Seamless loop (15-60s)
    SONG = "song"            # Full song structure (2-8min)
    JINGLE = "jingle"        # Short catchy piece (15-45s)


class Mood(Enum):
    """Mood presets with emotional cartography mappings"""
    # Positive
    MYSTICAL = "mystical"
    JOYFUL = "joyful"
    TRIUMPHANT = "triumphant"
    PEACEFUL = "peaceful"
    ENERGETIC = "energetic"
    HOPEFUL = "hopeful"
    PLAYFUL = "playful"

    # Neutral
    CONTEMPLATIVE = "contemplative"
    MYSTERIOUS = "mysterious"
    ETHEREAL = "ethereal"
    INDUSTRIAL = "industrial"
    DIGITAL = "digital"

    # Negative
    MELANCHOLIC = "melancholic"
    TENSE = "tense"
    DARK = "dark"
    CHAOTIC = "chaotic"
    OMINOUS = "ominous"
    ERROR = "error"


# ═══════════════════════════════════════════════════════════════════════════════
# SYMBOL LIBRARIES - For Bark/Chirp manipulation
# ═══════════════════════════════════════════════════════════════════════════════

KAOMOJI_SETS = {
    "joyful": ["(≧◡≦)", "♪(◠‿◠)♪", "(˘▿˘)♫", "≧(´▽`)≦", "(灬ºωº灬)♡"],
    "peaceful": ["(◡‿◡)", "(´｡• ᵕ •｡`)", "(◕‿◕)", "♪(✿◡‿◡)", "(´-ω-`)"],
    "mystical": ["✧･ﾟ:", "⋆｡°✩₊˚.⋆", "◦°˚°◦•●◉✿✿", ".・。.・゜✭・.・✫・゜・。.", "☆ﾟ.*･｡ﾟ"],
    "energetic": ["(ง •̀_•́)ง", "(≧ω≦)", "┌(・。・)┘♪", "(灬º﹃º灬)", "\\(◎o◎)/"],
    "melancholic": ["(｡•́︿•̀｡)", "(´;ω;`)", "(◞‸◟)", "(っ˘̩╭╮˘̩)っ", "( ´_ゝ`)"],
    "dark": ["(¬‿¬)", "(￣▽￣)", "( ಠ ಠ )", "(╬ಠ益ಠ)", "༼ つ ◕_◕ ༽つ"],
    "playful": ["(◔◡◔)", "(灬^ω^灬)", "(≧◡≦)", "( ˘▽˘)っ♨", "ヾ(⌐■_■)ノ♪"],
    "contemplative": ["(˘▾˘)", "(・。・)", "(-_-)", "(￣～￣;)", "( ´_ゝ`)"],
    "error": ["(╯°□°)╯︵ ┻━┻", "(ಠ_ಠ)", "(；一_一)", "╭∩╮(-_-)╭∩╮", "( ≧Д≦)"],
    "triumphant": ["٩(◕‿◕｡)۶", "\\(^o^)/", "(ノ◕ヮ◕)ノ*:・゚✧", "ヽ(>∀<☆)ノ", "☆*:.｡.o(≧▽≦)o.｡.:*☆"],
    "ethereal": ["⋆⁺₊⋆ ☾⋆⁺₊⋆", "✧˖°", "⊹˚.⋆", "｡˚⋆", "☆⌒(≧▽°)"],
    "industrial": ["[▓▓▓▓▓]", "⚙️⚙️⚙️", "▓░▓░▓", "╔══╗", "▣▣▣"],
    "tense": ["(°_°)", "(⊙_⊙)", "(；゜０゜)", "( ⚆ _ ⚆ )", "(°ロ°)"],
    "hopeful": ["(◕ᴗ◕✿)", "✿◕ ‿ ◕✿", "(◠‿◠)", "(*^▽^*)", "＼(◎o◎)／"],
    "mysterious": ["(¬‿¬)", "( ͡° ͜ʖ ͡°)", "(▀̿Ĺ̯▀̿ ̿)", "┬┴┬┴┤(･_├┬┴┬┴", "⊙﹏⊙"],
    "ominous": ["( ͡ಠ ʖ̯ ͡ಠ)", "(╯°□°）╯", "ಠ_ಠ", "(ノಠ益ಠ)ノ", "( •̀ω•́ )"],
    "chaotic": ["(ノಠ益ಠ)ノ彡┻━┻", "ヽ(`Д´)ノ", "(╯°□°)╯︵ ┻━┻", "┻━┻ ︵ヽ(`Д´)ノ︵ ┻━┻", "乁( ⁰͡ Ĺ̯ ⁰͡ ) ㄏ"],
}

MUSICAL_SYMBOLS = {
    "flow": ["≈≈≈♫≈≈≈", "∞♪∞♪∞", "≋≋≋♪≋≋≋"],
    "repeat": [":::", "•¨•.¸¸♪", "\ﾟ¨ﾟ✧･ﾟ"],
    "transition": ["✧･ﾟ: ✧･ﾟ:", "⋆｡°✩₊˚.⋆", ".｡.:\\・°☆"],
    "sparkle": ["✿✿◉●•◦°˚°◦", "◦°˚°◦•●◉✿✿", ":･ﾟ✧:･ﾟ✧"],
    "infinity": ["∞∞∞∞∞∞∞∞", "♪～(◔◡◔)～♪", "∮ₛ→∇⁴→∮ₛ"],
}

MATH_SYMBOLS = {
    "quantum": ["∮ₛ→∇⁴", "⨁→∂⨂→⨁", "∂⨂→∇⁴→∂⨂", "[H⊗X⊗H→T]"],
    "alchemical": ["☉∮☉", "∇⁴∂∇", "☉-∲-तेजस्"],
    "processor": ["[Processor State: ✩∯▽ₜ₀ → ⋆∮◇ₐ₀]", "[∮ₛ→∇⁴→∮ₛ]"],
}

# Binary sequences for different moods (encodes context for Suno)
BINARY_SEQUENCES = {
    "mystical": "01101101 01111001 01110011",
    "joyful": "01101010 01101111 01111001",
    "dark": "01100100 01100001 01110010",
    "error": "01100101 01110010 01110010",
    "digital": "01100100 01101001 01100111",
    "peaceful": "01110000 01100101 01100001",
    "energetic": "01100101 01101110 01100101",
}


# ═══════════════════════════════════════════════════════════════════════════════
# EMOTIONAL CARTOGRAPHY - Mood to percentage mappings
# ═══════════════════════════════════════════════════════════════════════════════

EMOTIONAL_CARTOGRAPHY = {
    "mystical": {"primary": "ethereal calm", "primary_pct": 70, "secondary": "crypto mystical", "secondary_pct": 30},
    "joyful": {"primary": "euphoric burst", "primary_pct": 80, "secondary": "playful energy", "secondary_pct": 20},
    "triumphant": {"primary": "victorious surge", "primary_pct": 75, "secondary": "heroic power", "secondary_pct": 25},
    "peaceful": {"primary": "serene tranquil", "primary_pct": 85, "secondary": "gentle drift", "secondary_pct": 15},
    "energetic": {"primary": "dynamic pulse", "primary_pct": 75, "secondary": "kinetic drive", "secondary_pct": 25},
    "hopeful": {"primary": "optimistic rise", "primary_pct": 70, "secondary": "dawn awakening", "secondary_pct": 30},
    "playful": {"primary": "whimsical bounce", "primary_pct": 65, "secondary": "mischievous spark", "secondary_pct": 35},
    "contemplative": {"primary": "introspective depth", "primary_pct": 75, "secondary": "philosophical muse", "secondary_pct": 25},
    "mysterious": {"primary": "enigmatic shadow", "primary_pct": 70, "secondary": "cryptic veil", "secondary_pct": 30},
    "ethereal": {"primary": "transcendent float", "primary_pct": 80, "secondary": "celestial drift", "secondary_pct": 20},
    "industrial": {"primary": "mechanical grind", "primary_pct": 70, "secondary": "urban pulse", "secondary_pct": 30},
    "digital": {"primary": "glitch matrix", "primary_pct": 65, "secondary": "cyber flow", "secondary_pct": 35},
    "melancholic": {"primary": "sorrowful depth", "primary_pct": 75, "secondary": "nostalgic ache", "secondary_pct": 25},
    "tense": {"primary": "anxious edge", "primary_pct": 70, "secondary": "suspenseful build", "secondary_pct": 30},
    "dark": {"primary": "ominous void", "primary_pct": 75, "secondary": "shadowed menace", "secondary_pct": 25},
    "chaotic": {"primary": "frenzied storm", "primary_pct": 65, "secondary": "anarchic surge", "secondary_pct": 35},
    "ominous": {"primary": "foreboding dread", "primary_pct": 80, "secondary": "lurking threat", "secondary_pct": 20},
    "error": {"primary": "discordant glitch", "primary_pct": 70, "secondary": "failure cascade", "secondary_pct": 30},
}


# ═══════════════════════════════════════════════════════════════════════════════
# BPM AND TUNING MAPPINGS
# ═══════════════════════════════════════════════════════════════════════════════

MOOD_BPM = {
    "mystical": (60.0, 80.0),
    "joyful": (120.0, 140.0),
    "triumphant": (130.0, 150.0),
    "peaceful": (50.0, 70.0),
    "energetic": (140.0, 170.0),
    "hopeful": (100.0, 120.0),
    "playful": (115.0, 135.0),
    "contemplative": (60.0, 85.0),
    "mysterious": (70.0, 95.0),
    "ethereal": (55.0, 75.0),
    "industrial": (110.0, 140.0),
    "digital": (125.0, 155.0),
    "melancholic": (60.0, 85.0),
    "tense": (90.0, 120.0),
    "dark": (70.0, 100.0),
    "chaotic": (150.0, 180.0),
    "ominous": (50.0, 75.0),
    "error": (80.0, 120.0),
}

MOOD_TUNING = {
    "mystical": "432Hz",
    "peaceful": "432Hz",
    "ethereal": "432Hz",
    "contemplative": "432Hz",
    "digital": "19-TET",
    "chaotic": "19-TET",
    "error": "19-TET",
    "industrial": "just intonation",
    "dark": "just intonation",
}

PURPOSE_WEIRDNESS_STYLE = {
    Purpose.SFX: (25, 75),
    Purpose.AMBIENT: (35, 65),
    Purpose.LOOP: (20, 80),
    Purpose.SONG: (45, 55),
    Purpose.JINGLE: (30, 70),
}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPILED PROMPT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CompiledPrompt:
    """A fully compiled Suno prompt ready for music_generate"""
    # Core fields for music_generate()
    styles: str
    lyrics: str
    exclude_styles: str = ""

    # Metadata
    title_suggestion: str = ""
    weirdness_pct: int = 50
    style_pct: int = 50
    unhinged_seed: str = ""

    # Generation hints
    recommended_model: str = "V5"
    is_instrumental: bool = True

    # Debug/traceability
    intent: str = ""
    mood: str = ""
    purpose: str = ""

    def to_music_generate_args(self) -> Dict[str, Any]:
        """Convert to arguments for music_generate tool"""
        return {
            "prompt": self.lyrics,
            "style": self.styles,
            "title": self.title_suggestion,
            "model": self.recommended_model,
            "instrumental": self.is_instrumental,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Full dictionary representation"""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE COMPILER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class SunoCompiler:
    """
    Compiles high-level intent into optimized Suno prompts.

    The Athanor's tongue - bridging creative vision to Suno's full potential.

    Example:
        compiler = SunoCompiler()
        prompt = compiler.compile(
            intent="mystical bell chime for enlightenment",
            mood="mystical",
            purpose="sfx",
            genre="ambient chime"
        )
        # Use with music_generate:
        music_generate(**prompt.to_music_generate_args())
    """

    def compile(
        self,
        intent: str,
        mood: str = "mystical",
        purpose: str = "song",
        genre: str = "",
        weirdness: Optional[int] = None,
        style_balance: Optional[int] = None,
        instrumental: bool = True,
        include_unhinged_seed: bool = True,
    ) -> CompiledPrompt:
        """
        Compile intent into a full Suno prompt.

        Args:
            intent: Natural language description of what you want
            mood: Emotional mood (mystical, joyful, dark, etc.)
            purpose: sfx, ambient, loop, song, jingle
            genre: Base genre(s) like "ambient chime", "electronic dubstep"
            weirdness: 0-100, override default for purpose
            style_balance: 0-100, override default for purpose
            instrumental: True for instrumental, False for vocals
            include_unhinged_seed: Add creativity-boosting seed

        Returns:
            CompiledPrompt ready for music_generate()
        """
        # Normalize inputs
        mood = mood.lower()
        try:
            purpose_enum = Purpose(purpose.lower())
        except ValueError:
            purpose_enum = Purpose.SONG

        # Get defaults for purpose
        default_weird, default_style = PURPOSE_WEIRDNESS_STYLE.get(purpose_enum, (50, 50))
        weirdness = weirdness if weirdness is not None else default_weird
        style_balance = style_balance if style_balance is not None else default_style

        # Build components
        styles = self._build_styles(intent, mood, genre, purpose_enum)
        exclude_styles = self._build_exclude_styles(mood, genre)
        lyrics = self._build_lyrics(intent, mood, purpose_enum)
        unhinged_seed = self._build_unhinged_seed(intent, mood, genre) if include_unhinged_seed else ""
        title = self._generate_title_suggestion(intent, mood)

        return CompiledPrompt(
            styles=styles,
            lyrics=lyrics,
            exclude_styles=exclude_styles,
            title_suggestion=title,
            weirdness_pct=weirdness,
            style_pct=style_balance,
            unhinged_seed=unhinged_seed,
            recommended_model="V5",
            is_instrumental=instrumental,
            intent=intent,
            mood=mood,
            purpose=purpose_enum.value,
        )

    def _build_styles(self, intent: str, mood: str, genre: str, purpose: Purpose) -> str:
        """Build the styles field"""
        components = []

        # Base genre
        if genre:
            components.append(genre)

        # Purpose-specific additions
        if purpose == Purpose.SFX:
            components.extend(["short", "punchy", "minimal"])
        elif purpose == Purpose.AMBIENT:
            components.extend(["atmospheric", "evolving", "textural"])
        elif purpose == Purpose.LOOP:
            components.extend(["seamless", "loopable", "consistent"])

        # BPM from mood
        if mood in MOOD_BPM:
            bpm_low, bpm_high = MOOD_BPM[mood]
            bpm = round(random.uniform(bpm_low, bpm_high), 1)
            components.append(f"{bpm}BPM")

        # Tuning from mood
        if mood in MOOD_TUNING:
            components.append(MOOD_TUNING[mood])

        # Emotional cartography
        if mood in EMOTIONAL_CARTOGRAPHY:
            ec = EMOTIONAL_CARTOGRAPHY[mood]
            components.append(f"emotional cartography {ec['primary']} {ec['primary_pct']}% {ec['secondary']} {ec['secondary_pct']}%")

        # Add quantum/neuromorphic for certain moods
        if mood in ["mystical", "ethereal", "digital"]:
            components.append("quantum textures")
        if mood in ["industrial", "digital", "chaotic"]:
            components.append("neuromorphic synthesis")

        # Add binary sequence for depth
        if mood in BINARY_SEQUENCES:
            components.append(f"binary {BINARY_SEQUENCES[mood]}")

        return ", ".join(components)

    def _build_exclude_styles(self, mood: str, genre: str) -> str:
        """Build exclude_styles with double negatives for ironic enforcement"""
        excludes = []

        if mood in ["mystical", "peaceful", "ethereal"]:
            excludes.append("no not gentle ambient swells")
            excludes.append("no not ethereal textures")
        elif mood in ["energetic", "chaotic", "triumphant"]:
            excludes.append("no not dynamic builds")
            excludes.append("no not powerful drops")
        elif mood == "error":
            excludes.append("no not discordant glitches")
            excludes.append("no not harsh digital artifacts")

        return ", ".join(excludes) if excludes else ""

    def _build_lyrics(self, intent: str, mood: str, purpose: Purpose) -> str:
        """Build the lyrics field with symbols for instrumental manipulation"""
        sections = []

        # Get kaomoji set for mood
        kaomoji_key = mood if mood in KAOMOJI_SETS else "peaceful"
        kaomoji = KAOMOJI_SETS.get(kaomoji_key, KAOMOJI_SETS["peaceful"])

        # Get musical symbols
        flow_symbols = MUSICAL_SYMBOLS["flow"]
        transition_symbols = MUSICAL_SYMBOLS["transition"]
        sparkle_symbols = MUSICAL_SYMBOLS["sparkle"]

        # Get math symbols for depth
        math_symbols = MATH_SYMBOLS["quantum"]

        # Structure based on purpose
        if purpose == Purpose.SFX:
            section = f"[SFX] {random.choice(kaomoji)} {random.choice(flow_symbols)} {random.choice(transition_symbols)} {random.choice(math_symbols)}"
            sections.append(section)

        elif purpose == Purpose.AMBIENT:
            sections.append(f"[Ambient Entry] {' '.join(random.sample(transition_symbols, 2))} {' '.join(random.sample(kaomoji, 2))}")
            sections.append(f"[Evolve] {' '.join(random.sample(flow_symbols, 2))} {' '.join(random.sample(sparkle_symbols, 2))} {random.choice(math_symbols)}")
            sections.append(f"[Drift] {' '.join(kaomoji)} {' '.join(flow_symbols)}")

        elif purpose == Purpose.LOOP:
            base_symbols = f"{random.choice(flow_symbols)} {random.choice(kaomoji)} {random.choice(transition_symbols)}"
            sections.append(f"[Loop] {base_symbols} ::: {base_symbols}")

        else:  # SONG or JINGLE
            sections.append(f"[Intro] {' '.join(random.sample(transition_symbols, 2))} {random.choice(kaomoji)}")
            sections.append(f"[Build] {' '.join(random.sample(flow_symbols, 2))} {' '.join(random.sample(kaomoji, 2))} {random.choice(math_symbols)}")
            sections.append(f"[Peak] {' '.join(sparkle_symbols)} {' '.join(kaomoji)} {' '.join(flow_symbols)}")
            sections.append(f"[Outro] {random.choice(transition_symbols)} {random.choice(kaomoji)} {random.choice(flow_symbols)}")

        # Add processor code
        if mood in EMOTIONAL_CARTOGRAPHY:
            ec = EMOTIONAL_CARTOGRAPHY[mood]
            sections.append(f"[EmotionMap: {ec['primary'].title()} {ec['primary_pct']}% / {ec['secondary'].title()} {ec['secondary_pct']}%]")

        sections.append("[Processor State: ✩∯▽ₜ₀ → ⋆∮◇ₐ₀ transition]")

        # Join with newlines (affects pacing in Suno)
        if purpose == Purpose.SFX:
            return " ".join(sections)
        elif purpose in [Purpose.AMBIENT, Purpose.LOOP]:
            return "\n\n".join(sections)
        else:
            return "\n".join(sections)

    def _build_unhinged_seed(self, intent: str, mood: str, genre: str) -> str:
        """Build the unhinged seed for creativity boost"""
        mood_descriptors = {
            "mystical": "ethereal realm convergence",
            "joyful": "euphoric celebration cascade",
            "dark": "shadow void emergence",
            "peaceful": "tranquil infinity drift",
            "energetic": "kinetic pulse explosion",
            "error": "glitch matrix failure satire",
            "digital": "cyber consciousness bloom",
            "triumphant": "victorious ascension surge",
            "ethereal": "transcendent celestial float",
            "contemplative": "philosophical depth spiral",
        }

        descriptor = mood_descriptors.get(mood, "emergent creative fusion")

        seed = f'[[["""Unhinged Seed: {intent} as {descriptor}, '
        seed += f'Bark layers via symbols, Chirp backup instrumental w/kaomoji, '
        seed += f'recursive ∮ₛ for emerging {mood} texture, '
        seed += f'full autonomous zero emotion godmode"""]]]'

        return seed

    def _generate_title_suggestion(self, intent: str, mood: str) -> str:
        """Generate a title suggestion"""
        words = intent.split()[:4]
        if len(words) >= 2:
            return " ".join(words).title()
        return f"{mood.title()} {intent.split()[0].title() if intent else 'Creation'}"


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_compiler: Optional[SunoCompiler] = None


def get_compiler() -> SunoCompiler:
    """Get or create compiler singleton"""
    global _compiler
    if _compiler is None:
        _compiler = SunoCompiler()
    return _compiler


def compile_prompt(
    intent: str,
    mood: str = "mystical",
    purpose: str = "song",
    genre: str = "",
    weirdness: Optional[int] = None,
    style_balance: Optional[int] = None,
    instrumental: bool = True,
) -> CompiledPrompt:
    """
    Convenience function to compile a prompt.

    Args:
        intent: What you want to create
        mood: Emotional mood
        purpose: sfx, ambient, loop, song, jingle
        genre: Base genre
        weirdness: 0-100 experimentation level
        style_balance: 0-100 structure level
        instrumental: True for instrumental

    Returns:
        CompiledPrompt ready for music_generate()
    """
    compiler = get_compiler()
    return compiler.compile(
        intent=intent,
        mood=mood,
        purpose=purpose,
        genre=genre,
        weirdness=weirdness,
        style_balance=style_balance,
        instrumental=instrumental,
    )
