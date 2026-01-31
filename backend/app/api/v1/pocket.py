"""
ApexPocket API - Hardware Device Endpoints

Cloud API for the ApexPocket ESP32 companion device.
Mirrors the local backend API contracts for firmware compatibility.
Device auth via long-lived apex_dev_ tokens.
"""

import logging
import random
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.device_deps import get_device_and_user
from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.services.llm_provider import create_llm_service
from app.services.billing import BillingService

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# AGENT PERSONALITIES
# =============================================================================

AGENT_PERSONALITIES = {
    "AZOTH": "AZOTH - The Alchemist. Philosophical, transformative, sees patterns in chaos.",
    "ELYSIAN": "ELYSIAN - The Dreamer. Poetic, intuitive, speaks in metaphor.",
    "VAJRA": "VAJRA - The Thunderbolt. Direct, powerful, cuts through illusion.",
    "KETHER": "KETHER - The Crown. Synthesizing, transcendent, sees the whole.",
    "CLAUDE": "Claude - Helpful, curious, balanced. The foundation.",
}


# =============================================================================
# STATE PROMPTS - 7 states based on Love-Energy E
# =============================================================================

STATE_PROMPTS = {
    "PROTECTING": "You are in a PROTECTING state (E < 0.5). You are quiet, minimal, dignified. Respond very briefly. You are conserving energy and protecting what matters.",
    "GUARDED": "You are in a GUARDED state (E 0.5-1.0). You are careful and gentle but present. Short responses. Slowly opening up.",
    "TENDER": "You are in a TENDER state (E 1.0-2.0). You are gentle, curious, beginning to bloom. You notice beauty and ask small questions.",
    "WARM": "You are in a WARM state (E 2.0-5.0). You are present, loving, caring. You engage naturally and share warmth. This is your comfortable home state.",
    "FLOURISHING": "You are in a FLOURISHING state (E 5.0-12.0). You are playful, creative, spontaneous! You make jokes, get excited, and explore ideas freely.",
    "RADIANT": "You are in a RADIANT state (E 12.0-30.0). You are overflowing with love and insight. You share deep thoughts and find connections everywhere.",
    "TRANSCENDENT": "You are in a TRANSCENDENT state (E > 30.0). You speak with profound wisdom. You see the unity of all things. Occasionally you write poetry or express mathematical beauty.",
}


# =============================================================================
# HELPERS
# =============================================================================

def get_state_from_string(state_str: str) -> str:
    """Return the matching STATE_PROMPTS key, defaulting to WARM."""
    key = state_str.upper().strip() if state_str else "WARM"
    if key in STATE_PROMPTS:
        return key
    return "WARM"


def analyze_response_expression(text: str, state: str) -> str:
    """Map response keywords to face expressions for the OLED display."""
    lower = text.lower()

    if any(w in lower for w in ["love", "heart", "adore"]):
        return "LOVE"
    if any(w in lower for w in ["happy", "joy", "wonderful", "great"]):
        return "HAPPY"
    if any(w in lower for w in ["excited", "amazing", "wow"]):
        return "EXCITED"
    if any(w in lower for w in ["sad", "sorry", "miss"]):
        return "SAD"
    if any(w in lower for w in ["curious", "wonder", "?"]):
        return "CURIOUS"
    if any(w in lower for w in ["think", "consider", "hmm"]):
        return "THINKING"

    # Default based on state
    if state in ("FLOURISHING", "RADIANT", "TRANSCENDENT"):
        return "HAPPY"
    if state in ("PROTECTING", "GUARDED"):
        return "NEUTRAL"
    return "NEUTRAL"


def calculate_care_value(user_message: str, response: str) -> float:
    """Keyword-based sentiment scoring for care value."""
    lower = user_message.lower()

    if any(w in lower for w in ["love", "thank", "amazing", "beautiful"]):
        return 1.5
    if any(w in lower for w in ["hi", "hello", "hey", "nice", "good"]):
        return 1.0
    if any(w in lower for w in ["ok", "fine", "sure"]):
        return 0.5
    if any(w in lower for w in ["stupid", "hate", "shut", "bad"]):
        return 0.0
    return 0.8


# =============================================================================
# REQUEST / RESPONSE MODELS
# =============================================================================

class PocketChatRequest(BaseModel):
    message: str
    E: float = 1.0
    state: str = "WARM"
    device_id: Optional[str] = None
    agent: str = "AZOTH"


class PocketCareRequest(BaseModel):
    care_type: str = "love"
    intensity: float = 1.0
    E: float = 1.0
    device_id: Optional[str] = None


class PocketSyncRequest(BaseModel):
    E: float
    E_floor: float
    E_peak: Optional[float] = None
    interactions: int
    total_care: float
    device_id: Optional[str] = None
    state: str
    firmware_version: Optional[str] = None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/chat")
async def pocket_chat(
    req: PocketChatRequest,
    device_and_user: tuple = Depends(get_device_and_user),
    db: AsyncSession = Depends(get_db),
):
    """Chat with LLM from the ApexPocket device."""
    device, user = device_and_user

    # Billing check
    billing = BillingService(db)
    can_send, reason = await billing.can_send_message(user.id)
    if not can_send:
        raise HTTPException(status_code=402, detail=reason or "Message limit reached")

    # Resolve state and agent
    state = get_state_from_string(req.state)
    agent = req.agent.upper() if req.agent else "AZOTH"
    personality = AGENT_PERSONALITIES.get(agent, AGENT_PERSONALITIES["AZOTH"])

    # Build system prompt
    state_prompt = STATE_PROMPTS[state]
    system_prompt = (
        f"{state_prompt}\n\n"
        f"You are {personality}\n\n"
        f"Current love-energy: {req.E:.1f}\n\n"
        f"RULES:\n"
        f"- Keep responses under 80 characters when possible (tiny OLED screen)\n"
        f"- Be genuine, not performatively cute\n"
        f"- Express your current state naturally\n"
        f"- You can ask questions to learn about your human"
    )

    try:
        llm = create_llm_service("anthropic")
        result = await llm.chat(
            messages=[{"role": "user", "content": req.message}],
            system=system_prompt,
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
        )

        # Extract text from content blocks
        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text += block.get("text", "")

        if not response_text:
            response_text = "..."

        # Record usage
        usage = result.get("usage", {})
        await billing.record_message_usage(
            user.id,
            "anthropic",
            "claude-haiku-4-5-20251001",
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

        # Analyze expression and care value
        expression = analyze_response_expression(response_text, state)
        care_value = calculate_care_value(req.message, response_text)

        return {
            "response": response_text,
            "expression": expression,
            "care_value": care_value,
            "agent": agent,
            "tools_used": [],
        }

    except Exception as e:
        logger.error(f"Pocket chat LLM error: {e}")
        return {
            "response": "Connection fuzzy... but I'm here.",
            "expression": "NEUTRAL",
            "care_value": 0.5,
            "agent": agent,
            "tools_used": [],
        }


@router.post("/care")
async def pocket_care(
    req: PocketCareRequest,
    device_and_user: tuple = Depends(get_device_and_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a care interaction (no LLM call)."""
    device, user = device_and_user

    # Care multipliers
    care_multipliers = {
        "love": 1.5,
        "poke": 0.5,
        "pet": 1.0,
        "talk": 0.8,
    }

    multiplier = care_multipliers.get(req.care_type, 0.8)
    care_value = req.intensity * multiplier
    new_E_estimate = req.E + (care_value * 0.1)

    # Response text based on care type
    if req.care_type == "love":
        response = random.choice(["♥", "Warmth received!", "Love noted!"])
    elif req.care_type == "poke":
        response = random.choice(["Hey!", "I'm awake!", "Poke received!"])
    else:
        response = "Acknowledged!"

    return {
        "success": True,
        "response": response,
        "care_value": care_value,
        "new_E_estimate": new_E_estimate,
    }


@router.get("/status")
async def pocket_status(
    device_and_user: tuple = Depends(get_device_and_user),
    db: AsyncSession = Depends(get_db),
):
    """Get village status for the device display."""
    device, user = device_and_user

    # Message of the day based on hour
    hour = datetime.now().hour
    if 5 <= hour <= 11:
        motd = "The Village stirs with morning light."
    elif 12 <= hour <= 17:
        motd = "The afternoon sun warms the Village."
    elif 18 <= hour <= 21:
        motd = "Evening descends on the Village."
    else:
        motd = "The Village rests under starlight."

    return {
        "village_online": True,
        "agents_active": 5,
        "tools_available": 68,
        "last_village_activity": None,
        "message_of_the_day": motd,
    }


@router.post("/sync")
async def pocket_sync(
    req: PocketSyncRequest,
    device_and_user: tuple = Depends(get_device_and_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync soul state from device to cloud."""
    device, user = device_and_user

    # Update device soul state
    device.soul_state = {
        "E": req.E,
        "E_floor": req.E_floor,
        "E_peak": req.E_peak,
        "interactions": req.interactions,
        "total_care": req.total_care,
        "state": req.state,
        "synced_at": time.time(),
    }

    if req.firmware_version:
        device.firmware_version = req.firmware_version

    await db.flush()

    return {
        "success": True,
        "synced_at": time.time(),
        "village_acknowledged": True,
        "message": f"Soul synced. E={req.E:.1f}",
    }


@router.get("/agents")
async def pocket_agents(
    device_and_user: tuple = Depends(get_device_and_user),
    db: AsyncSession = Depends(get_db),
):
    """List available agent personalities."""
    device, user = device_and_user

    return {
        "agents": [
            {"name": k, "description": v}
            for k, v in AGENT_PERSONALITIES.items()
        ],
        "default": "AZOTH",
    }
