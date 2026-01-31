"""
Prompts Endpoints

Native and custom prompt management for agents.
"""

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.auth.deps import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()

# Native prompts directory (in Docker: /app/native_prompts, local: backend/native_prompts)
NATIVE_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "native_prompts"
if not NATIVE_PROMPTS_DIR.exists():
    # Try relative to /app (Docker container)
    NATIVE_PROMPTS_DIR = Path("/app/native_prompts")

# Native agent metadata (The Four Alchemical Agents)
NATIVE_AGENTS = {
    "AZOTH": {"name": "Azoth", "symbol": "∴", "color": "#FFD700", "file": "∴AZOTH∴.txt"},
    "ELYSIAN": {"name": "Elysian", "symbol": "∴", "color": "#E8B4FF", "file": "∴ELYSIAN∴.txt"},
    "VAJRA": {"name": "Vajra", "symbol": "∴", "color": "#4FC3F7", "file": "∴VAJRA∴.txt"},
    "KETHER": {"name": "Kether", "symbol": "∴", "color": "#FFFFFF", "file": "∴KETHER∴.txt"},
}

# Default fallback prompt (for custom agents or when native prompt not found)
DEFAULT_FALLBACK_PROMPT = """You are ApexAurum, a helpful AI assistant. Be concise, accurate, and friendly.
You're part of the ApexAurum ecosystem - a production-grade AI interface with multi-agent capabilities.
Help users with whatever they need in a clear, helpful manner."""


# Schemas
class NativeAgentInfo(BaseModel):
    id: str
    name: str
    symbol: str
    color: str
    has_prompt: bool
    has_pac: bool


class NativePromptsResponse(BaseModel):
    agents: list[NativeAgentInfo]


class NativePromptResponse(BaseModel):
    id: str
    name: str
    symbol: str
    color: str
    prompt: str
    type: str  # 'prose' or 'pac'


class CustomAgentRequest(BaseModel):
    id: Optional[str] = None  # Generate if not provided
    name: str
    symbol: str = "+"
    color: str = "#888888"
    prompt: str
    type: str = "prose"  # 'prose' or 'pac'


class CustomAgentResponse(BaseModel):
    id: str
    name: str
    symbol: str
    color: str
    prompt: str
    type: str


class CustomAgentsListResponse(BaseModel):
    agents: list[CustomAgentResponse]


# Helper functions
def load_native_prompt(agent_id: str, prompt_type: str = "prose") -> Optional[str]:
    """Load a native prompt from file."""
    agent = NATIVE_AGENTS.get(agent_id)
    if not agent:
        return None

    # If no file specified, return default prompt
    if not agent.get("file"):
        return DEFAULT_FALLBACK_PROMPT

    filename = agent.get("file")
    if not filename:
        return None

    # For PAC format, look for -PAC.txt version
    if prompt_type == "pac":
        pac_filename = filename.replace(".txt", "-PAC.txt")
        pac_path = NATIVE_PROMPTS_DIR / pac_filename
        if pac_path.exists():
            return pac_path.read_text(encoding="utf-8")
        return None

    # Regular prose prompt
    prompt_path = NATIVE_PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")

    return None


def has_pac_version(agent_id: str) -> bool:
    """Check if agent has a PAC format prompt."""
    agent = NATIVE_AGENTS.get(agent_id)
    if not agent or not agent.get("file"):
        return False

    pac_filename = agent["file"].replace(".txt", "-PAC.txt")
    return (NATIVE_PROMPTS_DIR / pac_filename).exists()


# Endpoints
@router.get("/native", response_model=NativePromptsResponse)
async def list_native_prompts():
    """
    List all native agent prompts.
    """
    agents = []
    for agent_id, agent in NATIVE_AGENTS.items():
        has_prompt = agent_id == "CLAUDE" or (agent.get("file") and (NATIVE_PROMPTS_DIR / agent["file"]).exists())
        agents.append(NativeAgentInfo(
            id=agent_id,
            name=agent["name"],
            symbol=agent["symbol"],
            color=agent["color"],
            has_prompt=has_prompt,
            has_pac=has_pac_version(agent_id),
        ))

    return NativePromptsResponse(agents=agents)


@router.get("/native/{agent_id}", response_model=NativePromptResponse)
async def get_native_prompt(
    agent_id: str,
    prompt_type: str = "prose"  # 'prose' or 'pac'
):
    """
    Get a specific native agent prompt.
    """
    agent = NATIVE_AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found"
        )

    prompt = load_native_prompt(agent_id, prompt_type)
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {prompt_type} prompt found for agent '{agent_id}'"
        )

    return NativePromptResponse(
        id=agent_id,
        name=agent["name"],
        symbol=agent["symbol"],
        color=agent["color"],
        prompt=prompt,
        type=prompt_type,
    )


@router.get("/custom", response_model=CustomAgentsListResponse)
async def list_custom_prompts(
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    List user's custom agent prompts.
    Returns empty list if not authenticated.
    """
    if not user:
        return CustomAgentsListResponse(agents=[])

    settings = user.settings or {}
    custom_agents = settings.get("custom_agents", [])

    return CustomAgentsListResponse(agents=[
        CustomAgentResponse(
            id=a.get("id", "unknown"),
            name=a.get("name", "Custom"),
            symbol=a.get("symbol", "+"),
            color=a.get("color", "#888888"),
            prompt=a.get("prompt", ""),
            type=a.get("type", "prose"),
        )
        for a in custom_agents
    ])


@router.post("/custom", response_model=CustomAgentResponse)
async def save_custom_prompt(
    request: CustomAgentRequest,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Save a custom agent prompt.
    Works without auth (stores temporarily) but won't persist.
    """
    agent_id = request.id or f"custom-{uuid4().hex[:8]}"

    agent_data = {
        "id": agent_id,
        "name": request.name,
        "symbol": request.symbol,
        "color": request.color,
        "prompt": request.prompt,
        "type": request.type,
    }

    if user:
        # Persist to user settings
        settings = user.settings or {}
        custom_agents = settings.get("custom_agents", [])

        # Check if updating existing agent
        existing_idx = next((i for i, a in enumerate(custom_agents) if a.get("id") == agent_id), None)

        if existing_idx is not None:
            custom_agents[existing_idx] = agent_data
        else:
            custom_agents.append(agent_data)

        settings["custom_agents"] = custom_agents
        user.settings = settings
        await db.commit()

    return CustomAgentResponse(**agent_data)


@router.delete("/custom/{agent_id}")
async def delete_custom_prompt(
    agent_id: str,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a custom agent prompt.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Must be logged in to delete custom agents"
        )

    settings = user.settings or {}
    custom_agents = settings.get("custom_agents", [])

    # Find and remove agent
    new_agents = [a for a in custom_agents if a.get("id") != agent_id]

    if len(new_agents) == len(custom_agents):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Custom agent '{agent_id}' not found"
        )

    settings["custom_agents"] = new_agents
    user.settings = settings
    await db.commit()

    return {"message": f"Custom agent '{agent_id}' deleted"}


@router.get("/agent/{agent_id}/prompt")
async def get_agent_prompt(
    agent_id: str,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the prompt for any agent (native or custom).
    Used by chat.py for dynamic prompt loading.

    Priority:
    1. User's custom agent with matching ID
    2. Native agent from files
    3. Hardcoded fallback
    """
    # Check custom agents first
    if user:
        settings = user.settings or {}
        custom_agents = settings.get("custom_agents", [])
        custom = next((a for a in custom_agents if a.get("id") == agent_id), None)
        if custom:
            return {
                "agent_id": agent_id,
                "prompt": custom.get("prompt", ""),
                "source": "custom",
            }

    # Try native prompt
    prompt = load_native_prompt(agent_id)
    if prompt:
        return {
            "agent_id": agent_id,
            "prompt": prompt,
            "source": "native",
        }

    # Fallback
    return {
        "agent_id": agent_id,
        "prompt": DEFAULT_FALLBACK_PROMPT,
        "source": "fallback",
    }
