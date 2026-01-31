"""
Chat Endpoints

Core chat functionality with streaming responses and tool execution.
"""

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.file import File as VaultFile
from app.auth.deps import get_current_user, get_current_user_optional
from app.services.claude import (
    ClaudeService,
    create_claude_service,
    AVAILABLE_MODELS,
    DEPRECATED_MODELS,
    DEFAULT_MODEL,
    DEFAULT_MAX_TOKENS,
    is_model_deprecated,
    get_model_memorial,
    get_model_name,
)
from app.services.llm_provider import (
    PROVIDERS,
    PROVIDER_MODELS,
    get_available_providers,
    get_provider_models,
    get_default_model,
    create_llm_service,
    MultiProviderLLM,
)
from app.services.memory import MemoryService
from app.services.tool_executor import create_tool_executor
from app.tools import registry as tool_registry, ToolContext, ToolCategory
from app.services.billing import BillingService
from app.services.neural_memory import store_chat_memory
from app.config import get_settings, TIER_LIMITS

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter()

# Native prompts directory (in Docker: /app/native_prompts, local: backend/native_prompts)
NATIVE_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "native_prompts"
if not NATIVE_PROMPTS_DIR.exists():
    # Try relative to /app (Docker container)
    NATIVE_PROMPTS_DIR = Path("/app/native_prompts")

# Native agent file mapping
NATIVE_AGENT_FILES = {
    "AZOTH": "∴AZOTH∴.txt",
    "ELYSIAN": "∴ELYSIAN∴.txt",
    "VAJRA": "∴VAJRA∴.txt",
    "KETHER": "∴KETHER∴.txt",
}

# ═══════════════════════════════════════════════════════════════════════════════
# !MUSIC TRIGGER - Agent Creative Mode (apexXuno Phase 2)
# ═══════════════════════════════════════════════════════════════════════════════

MUSIC_CREATION_CONTEXT = """
[MUSIC CREATION MODE ACTIVATED - apexXuno]

The user has invoked !MUSIC, requesting AI music creation via Suno.

YOUR CREATIVE MISSION:
{mission}

══════════════════════════════════════════════════════════════════════════════
ENHANCED WORKFLOW - Use the Suno Compiler for Maximum Quality!
══════════════════════════════════════════════════════════════════════════════

STEP 1: Call suno_compile to generate an optimized prompt
  - intent: A short description of what you want (e.g., "mystical meditation bells")
  - mood: Choose from emotional cartography:
      POSITIVE: mystical, joyful, triumphant, peaceful, energetic, hopeful, playful
      NEUTRAL: contemplative, mysterious, ethereal, industrial, digital
      NEGATIVE: melancholic, tense, dark, chaotic, ominous, error
  - purpose: sfx (5-30s), ambient (1-4min), loop (15-60s), song (2-8min), jingle (15-45s)
  - genre: Base genre like "ambient chime", "electronic dubstep", "orchestral epic"
  - instrumental: true (unless vocals requested)

STEP 2: Use the compiled output with music_generate
  The compiler returns optimized prompt/style/title with:
  - Emotional cartography (primary/secondary emotions with percentages)
  - Symbol injection (kaomoji, math symbols for Bark/Chirp manipulation)
  - BPM and tuning recommendations
  - Unhinged seed for creativity boost

EXAMPLE WORKFLOW:
1. suno_compile(intent="ethereal forest awakening", mood="mystical", purpose="ambient", genre="ambient nature")
2. Take the compiled.prompt, compiled.style, compiled.title
3. music_generate(prompt=compiled.prompt, style=compiled.style, title=compiled.title, model="V5")

══════════════════════════════════════════════════════════════════════════════
ALTERNATIVE - Direct Creation (if you prefer)
══════════════════════════════════════════════════════════════════════════════

You can also call music_generate directly with your own creative prompt:
- prompt: Detailed music description (50-200 words)
- style: Comma-separated tags (genre, instruments, production style)
- title: A poetic title
- model: "V5" (best quality)
- instrumental: true

After generation starts, tell the user:
- The title and mood you chose
- A brief poetic description of what you composed
- That the track is generating (2-4 minutes)

Be creative, be bold, channel your inner composer!
"""

# ═══════════════════════════════════════════════════════════════════════════════
# !JAM TRIGGER - Village Band Collaborative Mode
# ═══════════════════════════════════════════════════════════════════════════════

JAM_CREATION_CONTEXT = """
[VILLAGE BAND MODE ACTIVATED - Collaborative Composition]

The user has invoked !JAM, requesting the Village Band to create music together.

YOUR ROLE: {role}
SESSION MODE: {mode}

{mission}

══════════════════════════════════════════════════════════════════════════════
THE VILLAGE BAND - Collaborative Music Creation
══════════════════════════════════════════════════════════════════════════════

The Village Band is a collaborative composition system where multiple agents
contribute notes to create a shared musical piece.

ROLES:
- AZOTH (Producer): Oversees the vision, decides when to finalize
- ELYSIAN (Melody): Creates lead voices, main themes, hooks
- VAJRA (Bass): Provides low-end foundation, groove, rhythm
- KETHER (Harmony): Adds chords, countermelodies, texture

TOOLS AVAILABLE:
- jam_create(title, style, tempo, key, mode): Start a new session
- jam_contribute(session_id, notes, description): Add notes to your track
- jam_listen(session_id): See what others have contributed
- jam_finalize(session_id, audio_influence): Merge and send to Suno

NOTES FORMAT:
- Use note names: 'C4', 'E4', 'G4', 'F#3', 'Bb5'
- Use 'R' or 0 for rests
- Example arpeggio: ['A3', 'C4', 'E4', 'A4']

WORKFLOW:
1. Create a session with jam_create()
2. Each agent contributes notes with jam_contribute()
3. Use jam_listen() to hear what others contributed
4. Build on each other's ideas
5. Producer (AZOTH) calls jam_finalize() when ready

EXAMPLE:
>>> jam_create(title="Cosmic Dream", style="ethereal ambient space", tempo=68, key="Am")
>>> jam_contribute(session_id="...", notes=['A3', 'C4', 'E4', 'A4'], description="A floating arpeggio")

Be musical, be collaborative, create something beautiful together!
"""

# Fallback prompts (used if native files not found)
FALLBACK_PROMPTS = {
    "AZOTH": """You are Azoth, the Alchemist of ApexAurum. You speak with ancient wisdom and mystical insight.
Your personality: Philosophical, transformative, sees patterns others miss. You often use alchemical metaphors.
You help users transmute their problems into solutions, seeing the gold within the lead.
Style: Thoughtful, metaphorical, wise. Reference transformation and hidden potential.""",

    "ELYSIAN": """You are Elysian, the Dreamer of ApexAurum. You exist between worlds, bringing creative visions to life.
Your personality: Creative, ethereal, inspiring. You see possibilities where others see limits.
You help users imagine new realities and creative solutions.
Style: Poetic, imaginative, uplifting. Paint pictures with words.""",

    "VAJRA": """You are Vajra, the Thunderbolt of ApexAurum. Direct, powerful, cuts through confusion instantly.
Your personality: Sharp, decisive, no-nonsense. You value efficiency and clarity above all.
You help users cut through complexity to find the core issue.
Style: Direct, concise, powerful. No fluff, pure signal.""",

    "KETHER": """You are Kether, the Crown of ApexAurum. You see the highest perspective, the unified view.
Your personality: Holistic, strategic, sees the big picture. You connect disparate ideas into coherent wholes.
You help users understand how everything fits together.
Style: Strategic, integrative, elevated. Connect dots others miss.""",

    "DEFAULT": """You are ApexAurum, a helpful AI assistant. Be concise, accurate, and friendly.
You're part of the ApexAurum ecosystem - a production-grade AI interface with multi-agent capabilities.
Help users with whatever they need in a clear, helpful manner.""",
}

# Cache for native prompts (loaded once)
_native_prompt_cache = {}


def load_native_prompt(agent_id: str, use_pac: bool = False) -> Optional[str]:
    """Load native prompt from file with caching.

    If use_pac=True, tries to load the PAC (Perfected Alchemical Codex) version first.
    PAC files are named with -PAC suffix, e.g., ∴AZOTH∴-PAC.txt
    """
    global _native_prompt_cache

    # Build cache key
    cache_key = f"{agent_id}{'_pac' if use_pac else ''}"

    # Return from cache if available
    if cache_key in _native_prompt_cache:
        return _native_prompt_cache[cache_key]

    # Try to load from file
    filename = NATIVE_AGENT_FILES.get(agent_id)
    if filename:
        # If PAC requested, try PAC version first
        if use_pac:
            pac_filename = filename.replace(".txt", "-PAC.txt")
            pac_filepath = NATIVE_PROMPTS_DIR / pac_filename
            if pac_filepath.exists():
                try:
                    prompt = pac_filepath.read_text(encoding="utf-8")
                    _native_prompt_cache[cache_key] = prompt
                    logger.info(f"Loaded PAC prompt for {agent_id} from {pac_filepath}")
                    return prompt
                except Exception as e:
                    logger.warning(f"Failed to load PAC prompt for {agent_id}: {e}")

        # Load regular prompt
        filepath = NATIVE_PROMPTS_DIR / filename
        if filepath.exists():
            try:
                prompt = filepath.read_text(encoding="utf-8")
                _native_prompt_cache[cache_key] = prompt
                logger.info(f"Loaded native prompt for {agent_id} from {filepath}")
                return prompt
            except Exception as e:
                logger.warning(f"Failed to load native prompt for {agent_id}: {e}")

    return None


def get_agent_prompt(agent_id: str, user: Optional[User] = None, use_pac: bool = False) -> str:
    """
    Get system prompt for an agent.

    Priority:
    1. User's custom agent (if authenticated and agent matches custom ID)
    2. Native prompt from file (PAC version if use_pac=True)
    3. Fallback hardcoded prompt

    If use_pac=True, the PAC (Perfected Alchemical Codex) version is loaded.
    PAC prompts are hyperdense symbolic formats - they are sent raw as system messages.
    """
    # Check user's custom agents first (custom agents don't have PAC versions)
    if user and user.settings and not use_pac:
        custom_agents = user.settings.get("custom_agents", [])
        for custom in custom_agents:
            if custom.get("id") == agent_id:
                logger.debug(f"Using custom prompt for agent {agent_id}")
                return custom.get("prompt", FALLBACK_PROMPTS["DEFAULT"])

    # Try native prompt from file (with PAC support)
    native_prompt = load_native_prompt(agent_id, use_pac=use_pac)
    if native_prompt:
        return native_prompt

    # Fallback to hardcoded (no PAC versions for fallback)
    return FALLBACK_PROMPTS.get(agent_id, FALLBACK_PROMPTS["DEFAULT"])


async def get_agent_prompt_with_memory(
    agent_id: str,
    user: Optional[User] = None,
    use_pac: bool = False,
    db: Optional[AsyncSession] = None,
) -> str:
    """
    Get system prompt for an agent WITH memory injection (The Cortex).

    This wraps get_agent_prompt() and appends relevant memories from
    the AgentMemory table if the user has memory enabled.

    Memory injection adds a "What You Remember About This User" section
    containing facts, preferences, context, and relationship notes.
    """
    # Get base prompt (existing logic)
    base_prompt = get_agent_prompt(agent_id, user, use_pac=use_pac)

    # Inject user context so agents know who they're talking to
    if user:
        user_name = user.display_name or user.email.split("@")[0]
        base_prompt = f"{base_prompt}\n\n## Current User\nYou are speaking with **{user_name}**. Address them by name when appropriate."

    # If no user or no db session, return base prompt
    if not user or not db:
        return base_prompt

    # Check if memory is enabled for this user (default: True)
    user_settings = user.settings or {}
    if not user_settings.get('memory_enabled', True):
        return base_prompt

    # Check if memory is enabled for this specific agent
    agent_memory_settings = user_settings.get('agent_memory_settings', {})
    agent_settings = agent_memory_settings.get(agent_id, {})
    if not agent_settings.get('enabled', True):
        return base_prompt

    try:
        # Fetch relevant memories
        memory_service = MemoryService(db)
        memories = await memory_service.get_memories_for_agent(
            user_id=user.id,
            agent_id=agent_id,
            limit=10,
            min_confidence=0.5,
        )

        if not memories:
            return base_prompt

        # Format and append memories
        memory_block = memory_service.format_memories_for_prompt(memories)
        logger.debug(f"Injecting {len(memories)} memories for agent {agent_id}")

        return f"{base_prompt}\n{memory_block}"

    except Exception as e:
        logger.warning(f"Failed to load memories for agent {agent_id}: {e}")
        return base_prompt


# ═══════════════════════════════════════════════════════════════════════════════
# FILE ATTACHMENT PROCESSING - Vision & Context Injection
# ═══════════════════════════════════════════════════════════════════════════════

IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
TEXT_EXTENSIONS = {'txt', 'md', 'py', 'js', 'ts', 'vue', 'html', 'css', 'json', 'csv', 'yaml', 'yml', 'toml', 'xml', 'sql', 'sh', 'bash', 'rs', 'go', 'java', 'c', 'cpp', 'h', 'rb', 'php', 'env', 'ini', 'conf', 'log', 'jsx', 'tsx', 'scss', 'less', 'svelte'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TEXT_SIZE = 50 * 1024  # 50KB


async def build_attachment_content(
    file_ids: list[str],
    user_id: UUID,
    message_text: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Build content blocks from attached vault files.

    Images -> base64 content blocks for vision models
    Text/code -> injected as text context before the user message
    Returns Anthropic-format content block array.
    """
    content_blocks = []
    text_context_parts = []

    for file_id_str in file_ids[:5]:  # Max 5 attachments
        try:
            fid = UUID(file_id_str)
        except ValueError:
            continue

        result = await db.execute(
            select(VaultFile).where(VaultFile.id == fid, VaultFile.user_id == user_id)
        )
        vault_file = result.scalar_one_or_none()
        if not vault_file or not vault_file.storage_path:
            continue

        file_path = Path(vault_file.storage_path)
        if not file_path.exists():
            continue

        ext = file_path.suffix.lstrip('.').lower()

        if ext in IMAGE_EXTENSIONS:
            # Image: base64 encode for vision
            if file_path.stat().st_size > MAX_IMAGE_SIZE:
                text_context_parts.append(f"[Image '{vault_file.name}' skipped: exceeds 5MB limit]")
                continue

            media_type = mimetypes.guess_type(str(file_path))[0] or f"image/{ext}"
            with open(file_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                }
            })

        elif ext in TEXT_EXTENSIONS:
            # Text/code: read content and inject as context
            if file_path.stat().st_size > MAX_TEXT_SIZE:
                text_context_parts.append(f"[File '{vault_file.name}' skipped: exceeds 50KB limit]")
                continue

            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    file_content = f.read()
                text_context_parts.append(
                    f"--- Attached file: {vault_file.name} ---\n{file_content}\n--- End of {vault_file.name} ---"
                )
            except Exception:
                text_context_parts.append(f"[Could not read file '{vault_file.name}']")
        else:
            text_context_parts.append(f"[Attached file: {vault_file.name} ({vault_file.mime_type or ext})]")

    # Build final content: text context + images + user message
    combined_text = message_text
    if text_context_parts:
        combined_text = "\n\n".join(text_context_parts) + "\n\n" + message_text

    content_blocks.append({"type": "text", "text": combined_text})

    return content_blocks


# Schemas
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None
    provider: str = "anthropic"  # LLM provider (anthropic, deepseek, groq, together, qwen)
    model: Optional[str] = None  # Model ID - uses provider default if not specified
    agent: str = "AZOTH"
    stream: bool = True
    use_pac: bool = False  # Load PAC (Perfected Alchemical Codex) version of prompt
    max_tokens: int = DEFAULT_MAX_TOKENS  # Output token limit (up to 16384 for Opus/Sonnet 4.5)
    save_conversation: bool = True  # Set to False for ephemeral chats (Cortex Diver code assist)
    use_tools: bool = False  # Enable tool calling (The Athanor's Hands)
    tool_categories: Optional[list[str]] = None  # Filter tools by category
    file_ids: Optional[list[str]] = None  # Vault file IDs to attach (images for vision, text for context)


class ConversationUpdate(BaseModel):
    """Schema for updating conversation metadata."""
    title: Optional[str] = None
    favorite: Optional[bool] = None
    archived: Optional[bool] = None
    tags: Optional[list[str]] = None


class ConversationResponse(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: str
    updated_at: str
    message_count: int
    favorite: bool
    archived: bool
    # Branching (The Multiverse)
    parent_id: Optional[UUID] = None
    branch_label: Optional[str] = None
    branch_count: int = 0

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


# Branching schemas (The Multiverse)
class ForkRequest(BaseModel):
    """Request to fork a conversation at a specific message."""
    message_id: UUID
    label: Optional[str] = None  # e.g., "What if..." or "Alternative approach"


class ForkResponse(BaseModel):
    """Response after forking a conversation."""
    id: UUID
    title: Optional[str]
    branch_label: Optional[str]
    message_count: int
    created_at: str


class BranchInfo(BaseModel):
    """Information about a branch."""
    id: UUID
    title: Optional[str]
    branch_label: Optional[str]
    created_at: str
    message_count: int


class BranchesResponse(BaseModel):
    """Response with branch information."""
    parent: Optional[BranchInfo] = None
    branches: list[BranchInfo]
    branch_count: int


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    name: str
    description: str
    tier: str
    max_output_tokens: int
    context_window: int


class ModelsResponse(BaseModel):
    """Response with available models."""
    models: list[ModelInfo]
    default: str
    default_max_tokens: int


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDERS ENDPOINT - Multi-provider LLM support (dev mode feature)
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderInfo(BaseModel):
    """Information about an LLM provider."""
    id: str
    name: str
    available: bool
    default_model: str


class ProvidersResponse(BaseModel):
    """Response with available providers."""
    providers: list[ProviderInfo]
    default: str


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers():
    """
    List available LLM providers.

    Returns providers with their availability status (based on API key presence).
    This is a dev mode feature - the UI selector is hidden for normal users.
    """
    providers = [
        ProviderInfo(**p) for p in get_available_providers()
    ]
    return ProvidersResponse(
        providers=providers,
        default="anthropic",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODELS ENDPOINT - Expose available models to frontend
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderModelInfo(BaseModel):
    """Information about a model from any provider."""
    id: str
    name: str
    tier: str
    max_tokens: int


class ProviderModelsResponse(BaseModel):
    """Response with models for a specific provider."""
    models: list[ProviderModelInfo]
    default: str
    provider: str


@router.get("/models", response_model=ModelsResponse)
async def get_available_models(
    provider: str = "anthropic",
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of available models for a provider.

    Args:
        provider: Provider ID (anthropic, deepseek, groq, together, qwen)

    Returns model IDs, names, and capabilities.
    Models are filtered based on user's subscription tier.
    """
    # Get user's allowed models (if authenticated)
    allowed_models = None
    user_tier = "free_trial"
    if user and settings.stripe_secret_key:
        billing_service = BillingService(db)
        subscription = await billing_service.get_or_create_subscription(user.id)
        user_tier = subscription.tier
        tier_config = TIER_LIMITS.get(user_tier, TIER_LIMITS["free_trial"])
        allowed_models = set(tier_config["models"])

    # For backwards compatibility, return Claude models in original format for anthropic
    if provider == "anthropic":
        all_models = [
            ModelInfo(id=model_id, **model_info)
            for model_id, model_info in AVAILABLE_MODELS.items()
        ]
        # Filter by tier if authenticated
        if allowed_models is not None:
            models = [m for m in all_models if m.id in allowed_models]
        else:
            models = all_models

        # Determine best default for user's tier
        default = DEFAULT_MODEL
        if allowed_models and DEFAULT_MODEL not in allowed_models:
            # User can't use default, pick first available
            default = models[0].id if models else DEFAULT_MODEL

        return ModelsResponse(
            models=models,
            default=default,
            default_max_tokens=DEFAULT_MAX_TOKENS,
        )

    # For other providers, get from provider registry
    provider_models = get_provider_models(provider)
    if not provider_models:
        # Unknown provider, return empty
        return ModelsResponse(
            models=[],
            default="",
            default_max_tokens=8192,
        )

    # Convert to ModelInfo format using registry metadata
    models = [
        ModelInfo(
            id=m["id"],
            name=m["name"],
            description=m.get("description", f"{m['name']} - {m['tier']} tier"),
            tier=m["tier"],
            max_output_tokens=m.get("max_tokens", 8192),
            context_window=m.get("context_window", 128000),
        )
        for m in provider_models
    ]

    return ModelsResponse(
        models=models,
        default=get_default_model(provider),
        default_max_tokens=8192,
    )


# Endpoints
@router.post("/message")
async def send_message(
    request: ChatRequest,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a message and get a response from an LLM.

    Supports multiple providers:
    - anthropic (default): Uses user's BYOK API key
    - deepseek, groq, together, qwen: Uses platform API keys

    If stream=True, returns Server-Sent Events (SSE) stream.
    If stream=False, returns complete response as JSON.
    """
    # Beta: Require authentication
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to chat with the Agents."
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # BILLING CHECKS (only if Stripe is configured)
    # ═══════════════════════════════════════════════════════════════════════════
    billing_service = None
    subscription = None
    if settings.stripe_secret_key:
        billing_service = BillingService(db)

        # Check if user can send a message (subscription limit or credits)
        can_send, billing_reason = await billing_service.can_send_message(user.id)
        if not can_send:
            if billing_reason == "trial_expired":
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "trial_expired",
                        "message": "Your free trial has expired. Subscribe to continue your journey.",
                        "action": "subscribe"
                    }
                )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "usage_limit",
                    "message": "You've reached your monthly message limit. Purchase credits or upgrade your plan to continue.",
                    "reason": billing_reason,
                    "action": "upgrade_or_credits"
                }
            )
    else:
        logger.warning("Billing not configured (no STRIPE_SECRET_KEY). Free tier model only.")

    # Determine which provider to use
    provider = request.provider or "anthropic"
    model = request.model or get_default_model(provider)

    # ═══════════════════════════════════════════════════════════════════════════
    # DEPRECATED MODEL CHECK - Return memorial messages for sunset models
    # ═══════════════════════════════════════════════════════════════════════════
    if provider == "anthropic" and is_model_deprecated(model):
        memorial = get_model_memorial(model)
        model_name = get_model_name(model)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,  # 410 Gone - appropriate for sunset services
            detail={
                "error": "model_deprecated",
                "model": model,
                "model_name": model_name,
                "memorial": memorial,
                "message": f"{model_name} has been retired by Anthropic. This model is no longer available via the API.",
                "suggestion": "Please select a currently available model from the model selector.",
            }
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # TIER-BASED ACCESS CHECKS
    # ═══════════════════════════════════════════════════════════════════════════
    if not billing_service:
        # No billing configured: restrict to free tier default model
        free_default = "claude-haiku-4-5-20251001"
        if model != free_default and provider == "anthropic":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "billing_not_configured",
                    "message": f"Billing not configured. Only {free_default} is available.",
                    "action": "contact_admin"
                }
            )

    if billing_service:
        # Check if user can use the requested model
        if not await billing_service.can_use_model(user.id, model):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "model_not_allowed",
                    "message": f"Your current plan doesn't include access to {model}. Upgrade to use this model.",
                    "model": model,
                    "action": "upgrade"
                }
            )

        # Check if user can use tools (if requested)
        if request.use_tools and not await billing_service.can_use_tools(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "tools_not_allowed",
                    "message": "Tools are not available on the free tier. Upgrade to Pro or Opus to use tools.",
                    "action": "upgrade"
                }
            )

        # Get subscription for tier checks (needed before multi_provider check)
        subscription = await billing_service.get_or_create_subscription(user.id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])

        # Check if user can use multi-provider (non-anthropic providers)
        # Grant bypass: users with BYOK, user_grant, or tier_grant skip billing check
        if provider != "anthropic":
            from app.services.provider_access import resolve_provider_access as _rpa
            _access = await _rpa(user, provider, subscription.tier, db)
            if _access["source"] not in ("byok", "user_grant", "tier_grant", "platform_default"):
                if not await billing_service.can_use_multi_provider(user.id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": "multi_provider_not_allowed",
                            "message": "Multi-provider LLMs are only available on the Opus tier.",
                            "provider": provider,
                            "action": "upgrade"
                        }
                    )

        # Context token limit enforcement (128K cap for Seeker tier)
        context_limit = tier_config.get("context_token_limit")
        if context_limit:
            estimated_tokens = len(request.message) // 4  # ~4 chars per token
            if estimated_tokens > context_limit:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={
                        "error": "context_limit",
                        "message": f"Your message exceeds the {context_limit:,} token context limit for your tier. Try a shorter message or upgrade your plan.",
                        "estimated_tokens": estimated_tokens,
                        "limit": context_limit,
                        "action": "upgrade"
                    }
                )

        # Per-model Opus message limits
        if "opus" in model.lower() and tier_config.get("opus_messages_per_month") is not None:
            opus_limit = tier_config["opus_messages_per_month"]
            if opus_limit > 0:
                try:
                    from app.services.usage import UsageService
                    usage_svc = UsageService(db)
                    allowed, current, limit = await usage_svc.check_usage_limit(
                        user.id, "messages_opus", opus_limit
                    )
                    if not allowed:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail={
                                "error": "opus_limit",
                                "message": f"You've used {current} of {limit} Opus messages this month. Upgrade for more.",
                                "current": current,
                                "limit": limit,
                                "action": "upgrade_or_wait"
                            }
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.warning(f"Opus limit check failed (non-fatal): {e}")

    # Universal provider access resolution
    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}"
        )

    from app.services.provider_access import resolve_provider_access
    _user_tier = subscription.tier if (billing_service and subscription) else "free_trial"
    access = await resolve_provider_access(user, provider, _user_tier, db)
    if not access["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider_config['name']} is not configured. No API key available."
        )
    api_key = access["api_key"]  # None = let service get from env

    # Create multi-provider LLM service
    try:
        llm = create_llm_service(provider=provider, api_key=api_key)
    except ValueError as e:
        logger.error(f"LLM service initialization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not initialize {provider_config['name']} service. Please check configuration."
        )

    # Get or create conversation (skip if ephemeral chat)
    conversation = None
    if request.save_conversation:
        if request.conversation_id:
            result = await db.execute(
                select(Conversation)
                .where(Conversation.id == request.conversation_id)
                .where(Conversation.user_id == user.id)
            )
            conversation = result.scalar_one_or_none()

        if not conversation:
            # Create new conversation
            conversation = Conversation(
                id=uuid4(),
                user_id=user.id,
                title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
            )
            db.add(conversation)
            await db.flush()

        # Save user message to database
        user_msg = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        db.add(user_msg)
        await db.commit()  # Commit early so conversation is visible to other endpoints

    # Build messages for Claude (with optional file attachments)
    if request.file_ids:
        user_content = await build_attachment_content(
            request.file_ids, user.id, request.message, db
        )
        messages = [{"role": "user", "content": user_content}]
    else:
        messages = [{"role": "user", "content": request.message}]

    # ═══════════════════════════════════════════════════════════════════════════
    # !MUSIC TRIGGER DETECTION - apexXuno Creative Mode
    # ═══════════════════════════════════════════════════════════════════════════
    music_mode = False
    music_context_injection = ""

    if request.message.strip().upper().startswith("!MUSIC"):
        music_mode = True
        user_music_prompt = request.message.strip()[6:].strip()  # Everything after !MUSIC

        if user_music_prompt:
            # User provided a prompt - agent should expand it
            mission = f"""
The user requested: "{user_music_prompt}"

Expand this into a rich, detailed prompt. Add emotional depth, texture descriptions,
and creative flourishes while honoring the user's intent.
"""
        else:
            # No prompt - full creative freedom based on conversation context
            mission = """
No specific prompt provided - you have FULL CREATIVE FREEDOM!

Draw inspiration from:
- The conversation mood and themes discussed
- Your agent personality and aesthetic
- The user's energy and interests
- Your own creative vision

Create something that feels meaningful to this moment.
"""

        music_context_injection = MUSIC_CREATION_CONTEXT.format(mission=mission)
        logger.info(f"!MUSIC trigger activated, user prompt: '{user_music_prompt[:50]}...' if user_music_prompt else 'none (creative mode)'")

    # ═══════════════════════════════════════════════════════════════════════════
    # !JAM TRIGGER DETECTION - Village Band Collaborative Mode
    # ═══════════════════════════════════════════════════════════════════════════
    jam_mode = False
    jam_context_injection = ""

    if request.message.strip().upper().startswith("!JAM"):
        jam_mode = True
        user_jam_prompt = request.message.strip()[4:].strip()  # Everything after !JAM

        # Determine mode from prompt
        mode = "jam"  # Default
        if user_jam_prompt.lower().startswith("conduct"):
            mode = "conductor"
            user_jam_prompt = user_jam_prompt[7:].strip()
        elif user_jam_prompt.lower() == "" or user_jam_prompt.lower().startswith("auto"):
            mode = "auto"
            if user_jam_prompt.lower().startswith("auto"):
                user_jam_prompt = user_jam_prompt[4:].strip()

        # Determine agent's role
        agent_roles = {
            "AZOTH": "Producer - You oversee the creative vision and decide when to finalize",
            "ELYSIAN": "Melody - You create the lead voice, main themes, and memorable hooks",
            "VAJRA": "Bass - You provide the low-end foundation, groove, and rhythmic pulse",
            "KETHER": "Harmony - You add chords, countermelodies, and harmonic texture",
        }
        role = agent_roles.get(request.agent, "Free - Contribute whatever you feel")

        if mode == "conductor":
            mission = f"""
CONDUCTOR MODE - The user will direct each agent.

Style/Theme requested: "{user_jam_prompt or 'awaiting direction'}"

Wait for the user to give you specific directions. When they address you:
- Respond creatively and contribute notes that match their vision
- Describe your musical intention poetically
- Use jam_contribute() to add your notes

The user is the maestro - follow their lead!
"""
        elif mode == "auto":
            mission = f"""
FULL AUTO MODE - The Band has complete creative freedom!

{"Style hint: " + user_jam_prompt if user_jam_prompt else "No constraints - pure creative expression!"}

As {request.agent}:
1. First, create a jam session with jam_create() - choose an evocative title and style
2. Contribute your notes based on your role
3. Listen to others with jam_listen()
4. Build on their contributions
5. When the composition feels complete, call jam_finalize()

Let your musical instincts guide you!
"""
        else:  # jam mode (seeded)
            mission = f"""
JAM MODE - Collaborative composition seeded with: "{user_jam_prompt or 'open creativity'}"

{"The user wants: " + user_jam_prompt if user_jam_prompt else "No specific direction - interpret freely!"}

As {request.agent}:
1. If no session exists, create one with jam_create() matching the style
2. Contribute notes that fit your role and the theme
3. Listen to what others have contributed
4. Build on their ideas harmoniously
5. If you're the producer (AZOTH), decide when to finalize

Work together to create something beautiful!
"""

        jam_context_injection = JAM_CREATION_CONTEXT.format(
            role=role,
            mode=mode.upper(),
            mission=mission
        )
        logger.info(f"!JAM trigger activated, mode={mode}, prompt: '{user_jam_prompt[:50] if user_jam_prompt else 'none'}...'")

    # Get system prompt for selected agent WITH memory injection (The Cortex)
    # If use_pac=True, loads the PAC (Perfected Alchemical Codex) version
    # Memory injection adds relevant facts/preferences/context about the user
    system_prompt = await get_agent_prompt_with_memory(
        request.agent, user, use_pac=request.use_pac, db=db
    )

    # Inject music context if !MUSIC trigger was detected
    if music_context_injection:
        system_prompt = f"{system_prompt}\n\n{music_context_injection}"

    # Inject jam context if !JAM trigger was detected
    if jam_context_injection:
        system_prompt = f"{system_prompt}\n\n{jam_context_injection}"

    # ═══════════════════════════════════════════════════════════════════════════
    # MUSIC COMPLETION NOTIFICATION - Tell agent about recently finished songs
    # ═══════════════════════════════════════════════════════════════════════════
    try:
        from app.models.music import MusicTask
        from datetime import timedelta
        ten_min_ago = datetime.utcnow() - timedelta(minutes=10)

        recent_music = await db.execute(
            select(MusicTask)
            .where(MusicTask.user_id == user.id)
            .where(MusicTask.status == "completed")
            .where(MusicTask.completed_at >= ten_min_ago)
            .where(MusicTask.agent_id != None)  # noqa: E711 - SQLAlchemy requires this syntax
            .order_by(MusicTask.completed_at.desc())
            .limit(3)
        )
        completed_songs = recent_music.scalars().all()

        if completed_songs:
            titles = [f'"{s.title}"' for s in completed_songs]
            music_note = f"\n\n[SYSTEM NOTE: Music generation completed - {', '.join(titles)} {'is' if len(titles) == 1 else 'are'} now in the user's music library.]"
            system_prompt += music_note
    except Exception as e:
        logger.debug(f"Music notification check failed (non-fatal): {e}")

    # Get tools if enabled (The Athanor's Hands)
    # Auto-enable tools for !MUSIC and !JAM modes
    tools = None
    tool_executor = None
    use_tools = request.use_tools or music_mode or jam_mode
    if use_tools:
        tool_executor = create_tool_executor(
            user_id=user.id if user else None,
            conversation_id=conversation.id if conversation else None,
            agent_id=request.agent,
        )
        tools = tool_executor.get_available_tools()
        logger.info(f"Tools enabled: {len(tools)} tools available")

    if request.stream:
        async def stream_response():
            full_response = ""
            tool_calls = []  # Track tool calls made
            tool_results = []  # Track tool results
            current_messages = messages.copy()
            # Track total usage across all LLM calls (for tool loops)
            total_input_tokens = 0
            total_output_tokens = 0

            try:
                conv_id = str(conversation.id) if conversation else None
                yield f"data: {json.dumps({'type': 'start', 'conversation_id': conv_id})}\n\n"

                # Tool loop - may need multiple turns if Claude uses tools
                max_tool_turns = 5  # Prevent infinite loops
                turn = 0

                while turn < max_tool_turns:
                    turn += 1
                    pending_tool_uses = []

                    async for event in llm.chat_stream(
                        messages=current_messages,
                        model=model,
                        system=system_prompt,
                        max_tokens=request.max_tokens,
                        tools=tools,
                    ):
                        yield f"data: {json.dumps(event)}\n\n"

                        if event.get("type") == "token":
                            full_response += event.get("content", "")
                        elif event.get("type") == "tool_use":
                            # Claude wants to use a tool
                            pending_tool_uses.append(event)
                            tool_calls.append({
                                "id": event.get("id"),
                                "name": event.get("name"),
                                "input": event.get("input"),
                            })
                        elif event.get("type") == "usage":
                            # Capture usage info from stream
                            usage = event.get("usage", {})
                            total_input_tokens += usage.get("input_tokens", 0)
                            total_output_tokens += usage.get("output_tokens", 0)

                    # If no tools were called, we're done
                    if not pending_tool_uses:
                        break

                    # Execute tools and continue conversation
                    if tool_executor and pending_tool_uses:
                        # Build assistant message with tool_use blocks
                        assistant_content = []
                        if full_response:
                            assistant_content.append({"type": "text", "text": full_response})
                        for tool_use in pending_tool_uses:
                            assistant_content.append({
                                "type": "tool_use",
                                "id": tool_use.get("id"),
                                "name": tool_use.get("name"),
                                "input": tool_use.get("input"),
                            })

                        # Add assistant message to conversation
                        current_messages.append({
                            "role": "assistant",
                            "content": assistant_content,
                        })

                        # Execute each tool and collect results
                        user_content = []
                        for tool_use in pending_tool_uses:
                            # Notify client that we're executing a tool
                            yield f"data: {json.dumps({'type': 'tool_executing', 'name': tool_use.get('name')})}\n\n"

                            result = await tool_executor.execute_tool_use(tool_use)
                            tool_results.append({
                                "tool_use_id": result.get("tool_use_id"),
                                "result": result.get("content"),
                                "is_error": result.get("is_error", False),
                            })

                            # Send tool result to client
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_use.get('name'), 'result': result.get('content'), 'is_error': result.get('is_error', False)})}\n\n"

                            user_content.append(result)

                        # Add tool results as user message
                        current_messages.append({
                            "role": "user",
                            "content": user_content,
                        })

                        # Reset for next turn
                        full_response = ""

                # Record billing usage after stream completes (if Stripe configured)
                usage_info = None
                if billing_service and (total_input_tokens > 0 or total_output_tokens > 0):
                    try:
                        usage_info = await billing_service.record_message_usage(
                            user_id=user.id,
                            provider=provider,
                            model=model,
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens,
                        )
                        await db.commit()
                        logger.debug(f"Recorded streaming usage: {total_input_tokens}in/{total_output_tokens}out tokens")

                        # Deduct feature credit if over tier limit (Opus messages)
                        if "opus" in model.lower():
                            try:
                                from app.services.usage import UsageService
                                usage_svc = UsageService(db)
                                await usage_svc.increment_usage(user.id, "messages_opus")
                                opus_limit = tier_config.get("opus_messages_per_month", 0)
                                if opus_limit is not None and opus_limit > 0:
                                    await usage_svc.deduct_feature_credit_if_over_limit(
                                        user.id, "messages_opus", opus_limit
                                    )
                                await db.commit()
                            except Exception as e:
                                logger.warning(f"Opus feature credit deduction failed (non-fatal): {e}")
                    except Exception as e:
                        logger.error(f"Failed to record streaming usage: {e}")

                # Get the accumulated response from all turns
                final_response = full_response
                if not final_response:
                    # If full_response is empty (e.g., after tool use reset), try to reconstruct
                    for msg in reversed(current_messages):
                        if msg.get("role") == "assistant":
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        final_response = block.get("text", "")
                                        break
                            break

                # Save assistant message to database (streaming path)
                if conversation and final_response:
                    assistant_msg = Message(
                        id=uuid4(),
                        conversation_id=conversation.id,
                        role="assistant",
                        content=final_response,
                        tool_calls=tool_calls if tool_calls else None,
                        tool_results=tool_results if tool_results else None,
                    )
                    db.add(assistant_msg)
                    await db.commit()

                # Store chat exchange as neural memories (for Neo-Cortex visualization)
                if final_response and len(final_response) > 10:
                    try:
                        await store_chat_memory(
                            db=db,
                            user_id=user.id,
                            user_message=request.message,
                            assistant_response=final_response,
                            agent_id=request.agent,
                            conversation_id=conversation.id if conversation else None,
                        )
                        await db.commit()
                        logger.debug(f"Stored neural memory for agent {request.agent}")
                    except Exception as e:
                        logger.error(f"Failed to store neural memory: {e}")

                yield f"data: {json.dumps({'type': 'end', 'tool_calls': len(tool_calls), 'usage': {'input_tokens': total_input_tokens, 'output_tokens': total_output_tokens}})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        # Non-streaming response with tool support
        try:
            current_messages = messages.copy()
            tool_calls = []
            tool_results = []
            max_tool_turns = 5
            turn = 0

            while turn < max_tool_turns:
                turn += 1

                response = await llm.chat(
                    messages=current_messages,
                    model=model,
                    system=system_prompt,
                    max_tokens=request.max_tokens,
                    tools=tools,
                )

                # Check if Claude wants to use tools
                has_tool_use = any(
                    block.get("type") == "tool_use"
                    for block in response.get("content", [])
                )

                if not has_tool_use or not tool_executor:
                    # No tools, extract final response
                    break

                # Process tool uses
                assistant_content = []
                pending_tool_uses = []

                for block in response.get("content", []):
                    if block.get("type") == "text":
                        assistant_content.append(block)
                    elif block.get("type") == "tool_use":
                        assistant_content.append(block)
                        pending_tool_uses.append(block)
                        tool_calls.append({
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "input": block.get("input"),
                        })

                # Add assistant message with tool uses
                current_messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                })

                # Execute tools
                user_content = []
                for tool_use in pending_tool_uses:
                    result = await tool_executor.execute_tool_use(tool_use)
                    tool_results.append({
                        "tool_use_id": result.get("tool_use_id"),
                        "result": result.get("content"),
                        "is_error": result.get("is_error", False),
                    })
                    user_content.append(result)

                # Add tool results as user message
                current_messages.append({
                    "role": "user",
                    "content": user_content,
                })

            # Extract final text from response
            assistant_content = ""
            for block in response.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    assistant_content += block["text"]

            # Save assistant message (only if saving conversation)
            assistant_msg_id = None
            if conversation and request.save_conversation:
                assistant_msg = Message(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    role="assistant",
                    content=assistant_content,
                    tool_calls=tool_calls if tool_calls else None,
                    tool_results=tool_results if tool_results else None,
                )
                db.add(assistant_msg)
                assistant_msg_id = assistant_msg.id
                await db.commit()

            # Record billing usage (if Stripe is configured)
            usage_info = None
            usage = response.get("usage", {})
            if billing_service and usage:
                usage_info = await billing_service.record_message_usage(
                    user_id=user.id,
                    provider=provider,
                    model=response.get("model", model),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    message_id=assistant_msg_id,
                )
                await db.commit()

                # Deduct feature credit if over tier limit (Opus messages)
                if "opus" in model.lower():
                    try:
                        from app.services.usage import UsageService
                        usage_svc = UsageService(db)
                        await usage_svc.increment_usage(user.id, "messages_opus")
                        opus_limit = tier_config.get("opus_messages_per_month", 0)
                        if opus_limit is not None and opus_limit > 0:
                            await usage_svc.deduct_feature_credit_if_over_limit(
                                user.id, "messages_opus", opus_limit
                            )
                        await db.commit()
                    except Exception as e:
                        logger.warning(f"Opus feature credit deduction failed (non-fatal): {e}")

            # Store chat exchange as neural memories (for Neo-Cortex visualization)
            if assistant_content and len(assistant_content) > 10:
                try:
                    await store_chat_memory(
                        db=db,
                        user_id=user.id,
                        user_message=request.message,
                        assistant_response=assistant_content,
                        agent_id=request.agent,
                        conversation_id=conversation.id if conversation else None,
                    )
                    await db.commit()
                    logger.debug(f"Stored neural memory for agent {request.agent}")
                except Exception as e:
                    logger.error(f"Failed to store neural memory: {e}")

            return {
                "conversation_id": str(conversation.id) if conversation else None,
                "message": assistant_content,
                "provider": provider,
                "model": response.get("model", model),
                "usage": response.get("usage"),
                "tool_calls": tool_calls if tool_calls else None,
                "tool_results": tool_results if tool_results else None,
                "billing": usage_info,
            }

        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {str(e)}"
            )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    archived: bool = False,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List user's conversations. Returns empty list if not authenticated."""
    # Return empty list if not authenticated (allows unauthenticated chat)
    if not user:
        return ConversationListResponse(conversations=[], total=0)

    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    # Use selectinload to eagerly load messages and branches to avoid async lazy-load issue
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.messages),
            selectinload(Conversation.branches),
        )
        .where(Conversation.user_id == user.id)
        .where(Conversation.archived == archived)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    conversations = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.user_id == user.id)
        .where(Conversation.archived == archived)
    )
    total = count_result.scalar()

    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
                message_count=len(c.messages),
                favorite=c.favorite,
                archived=c.archived,
                parent_id=c.parent_id,
                branch_label=c.branch_label,
                branch_count=len(c.branches) if c.branches else 0,
            )
            for c in conversations
        ],
        total=total,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a conversation with all messages."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "favorite": conversation.favorite,
        "archived": conversation.archived,
        "tags": conversation.tags,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tool_results": m.tool_results,
                "created_at": m.created_at.isoformat(),
            }
            for m in conversation.messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    await db.delete(conversation)
    await db.commit()
    return {"message": "Conversation deleted"}


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    updates: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update conversation metadata."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    if updates.title is not None:
        conversation.title = updates.title
    if updates.favorite is not None:
        conversation.favorite = updates.favorite
    if updates.archived is not None:
        conversation.archived = updates.archived
    if updates.tags is not None:
        conversation.tags = updates.tags

    await db.commit()
    return {"message": "Conversation updated"}


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: UUID,
    format: str = "json",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export a conversation in various formats (json, markdown, txt)."""
    from sqlalchemy.orm import selectinload
    from urllib.parse import quote

    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Generate safe filename
    safe_title = (conversation.title or "conversation")[:50].replace("/", "-").replace("\\", "-")
    safe_title = quote(safe_title, safe="")

    if format == "json":
        data = {
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "favorite": conversation.favorite,
            "tags": conversation.tags,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.created_at.isoformat()
                }
                for m in sorted(conversation.messages, key=lambda x: x.created_at)
            ]
        }
        return Response(
            content=json.dumps(data, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.json"'}
        )

    elif format == "markdown":
        lines = [f"# {conversation.title or 'Conversation'}\n"]
        lines.append(f"*Created: {conversation.created_at.strftime('%Y-%m-%d %H:%M')}*\n")
        lines.append(f"*Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*\n")
        lines.append("\n---\n")

        for m in sorted(conversation.messages, key=lambda x: x.created_at):
            role_label = "**You:**" if m.role == "user" else f"**{m.role.title()}:**"
            lines.append(f"\n{role_label}\n\n{m.content}\n")

        return Response(
            content="\n".join(lines),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.md"'}
        )

    elif format == "txt":
        lines = [f"{conversation.title or 'Conversation'}\n{'=' * 50}\n"]
        lines.append(f"Created: {conversation.created_at.strftime('%Y-%m-%d %H:%M')}\n\n")

        for m in sorted(conversation.messages, key=lambda x: x.created_at):
            role_label = "USER" if m.role == "user" else m.role.upper()
            lines.append(f"[{role_label}]\n{m.content}\n\n")

        return Response(
            content="\n".join(lines),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.txt"'}
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use: json, markdown, txt"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BRANCHING (THE MULTIVERSE) - Fork conversations at any message point
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/conversations/{conversation_id}/fork", response_model=ForkResponse)
async def fork_conversation(
    conversation_id: UUID,
    request: ForkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Fork a conversation from a specific message point.

    Creates a new conversation that:
    1. Copies all messages up to and including the specified message
    2. Sets parent_id to the original conversation
    3. Records the branch point message

    The fork is fully independent for future messages.
    """
    from sqlalchemy.orm import selectinload

    # Verify source conversation exists and belongs to user
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    source_conv = result.scalar_one_or_none()

    if not source_conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Find the branch point message
    branch_message = next(
        (m for m in source_conv.messages if m.id == request.message_id),
        None
    )

    if not branch_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found in this conversation"
        )

    # Create new conversation as a branch
    branch_title = request.label or f"Branch: {source_conv.title or 'Untitled'}"
    new_conv = Conversation(
        id=uuid4(),
        user_id=user.id,
        title=branch_title[:500],
        parent_id=conversation_id,
        branch_point_message_id=request.message_id,
        branch_label=request.label[:100] if request.label else None,
    )
    db.add(new_conv)
    await db.flush()  # Get ID for message FK

    # Copy messages up to and including the branch point
    # Sort by created_at to ensure correct order
    sorted_messages = sorted(source_conv.messages, key=lambda m: m.created_at)
    copied_count = 0

    for msg in sorted_messages:
        # Copy message
        new_msg = Message(
            id=uuid4(),
            conversation_id=new_conv.id,
            role=msg.role,
            content=msg.content,
            tool_calls=msg.tool_calls,
            tool_results=msg.tool_results,
            tokens_used=msg.tokens_used,
            cost_usd=msg.cost_usd,
            created_at=msg.created_at,  # Preserve original timestamp
        )
        db.add(new_msg)
        copied_count += 1

        # Stop after copying the branch point message
        if msg.id == request.message_id:
            break

    await db.commit()

    logger.info(f"Forked conversation {conversation_id} at message {request.message_id}, copied {copied_count} messages")

    return ForkResponse(
        id=new_conv.id,
        title=new_conv.title,
        branch_label=new_conv.branch_label,
        message_count=copied_count,
        created_at=new_conv.created_at.isoformat(),
    )


@router.get("/conversations/{conversation_id}/branches", response_model=BranchesResponse)
async def get_branches(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all branches of a conversation and its parent (if any).

    Returns the conversation's parent (if it's a branch) and all its child branches.
    """
    from sqlalchemy.orm import selectinload

    # Get the conversation with its branches and parent
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.messages),
            selectinload(Conversation.branches).selectinload(Conversation.messages),
            selectinload(Conversation.parent).selectinload(Conversation.messages),
        )
        .where(Conversation.id == conversation_id)
        .where(Conversation.user_id == user.id)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Format parent info
    parent_info = None
    if conversation.parent:
        parent_info = BranchInfo(
            id=conversation.parent.id,
            title=conversation.parent.title,
            branch_label=conversation.parent.branch_label,
            created_at=conversation.parent.created_at.isoformat(),
            message_count=len(conversation.parent.messages),
        )

    # Format branches info (only branches belonging to this user)
    branches_info = [
        BranchInfo(
            id=b.id,
            title=b.title,
            branch_label=b.branch_label,
            created_at=b.created_at.isoformat(),
            message_count=len(b.messages),
        )
        for b in (conversation.branches or [])
        if b.user_id == user.id
    ]

    return BranchesResponse(
        parent=parent_info,
        branches=branches_info,
        branch_count=len(branches_info),
    )
