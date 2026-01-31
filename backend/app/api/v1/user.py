"""
User Endpoints

User profile, settings, and API key management.
Multi-provider BYOK support for all 6 LLM providers.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import anthropic
from openai import OpenAI, AuthenticationError as OpenAIAuthError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from sqlalchemy import select

from app.config import get_settings, TIER_LIMITS
from app.database import get_db
from app.models.billing import Subscription
from app.models.user import User
from app.auth.deps import get_current_user
from app.services.encryption import encrypt_value, decrypt_value, mask_api_key
from app.services.llm_provider import PROVIDERS

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# Provider key format hints for UI
PROVIDER_KEY_HINTS = {
    "anthropic": "sk-ant-...",
    "deepseek": "sk-...",
    "groq": "gsk_...",
    "together": "...",
    "qwen": "sk-...",
    "moonshot": "sk-...",
}

# Console URLs for each provider
PROVIDER_CONSOLE_URLS = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "groq": "https://console.groq.com/keys",
    "together": "https://api.together.ai/settings/api-keys",
    "qwen": "https://dashscope.console.aliyun.com",
    "moonshot": "https://platform.moonshot.cn/console/api-keys",
}


# Schemas
class UserProfileResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    created_at: str
    settings: dict

    class Config:
        from_attributes = True


class UserProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    settings: Optional[dict] = None


class UsageResponse(BaseModel):
    total_messages: int
    total_tokens: int
    total_cost_usd: float
    conversations_count: int
    agents_spawned: int
    music_generated: int


# Endpoints
@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
):
    """Get current user's profile."""
    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at.isoformat(),
        settings=user.settings,
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: UserProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    if request.display_name is not None:
        user.display_name = request.display_name

    if request.settings is not None:
        # Merge settings (don't replace entirely)
        current_settings = user.settings or {}
        current_settings.update(request.settings)
        user.settings = current_settings

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at.isoformat(),
        settings=user.settings,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's usage statistics."""
    from sqlalchemy import func, select
    from app.models.conversation import Conversation, Message
    from app.models.agent import Agent
    from app.models.music import MusicTask

    # Count conversations
    conv_result = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.user_id == user.id)
    )
    conversations_count = conv_result.scalar() or 0

    # Count messages and sum tokens/cost
    msg_result = await db.execute(
        select(
            func.count(Message.id),
            func.coalesce(func.sum(Message.tokens_used), 0),
            func.coalesce(func.sum(Message.cost_usd), 0)
        )
        .join(Conversation)
        .where(Conversation.user_id == user.id)
    )
    msg_stats = msg_result.one()
    total_messages = msg_stats[0] or 0
    total_tokens = msg_stats[1] or 0
    total_cost = float(msg_stats[2] or 0)

    # Count agents
    agent_result = await db.execute(
        select(func.count(Agent.id))
        .where(Agent.user_id == user.id)
    )
    agents_spawned = agent_result.scalar() or 0

    # Count music tasks
    music_result = await db.execute(
        select(func.count(MusicTask.id))
        .where(MusicTask.user_id == user.id)
    )
    music_generated = music_result.scalar() or 0

    return UsageResponse(
        total_messages=total_messages,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        conversations_count=conversations_count,
        agents_spawned=agents_spawned,
        music_generated=music_generated,
    )


@router.get("/preferences")
async def get_preferences(
    user: User = Depends(get_current_user),
):
    """Get user preferences (subset of settings)."""
    settings = user.settings or {}
    return {
        "default_model": settings.get("default_model", "claude-3-haiku-20240307"),
        "cache_strategy": settings.get("cache_strategy", "balanced"),
        "context_strategy": settings.get("context_strategy", "adaptive"),
        "theme": settings.get("theme", "dark"),
        "default_agent": settings.get("default_agent", "AZOTH"),
    }


@router.put("/preferences")
async def update_preferences(
    preferences: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences."""
    current_settings = user.settings or {}
    current_settings.update(preferences)
    user.settings = current_settings

    return {"message": "Preferences updated"}


# ═══════════════════════════════════════════════════════════════════════════════
# API KEY MANAGEMENT - Multi-Provider BYOK (Bring Your Own Key)
# ═══════════════════════════════════════════════════════════════════════════════

class ApiKeyRequest(BaseModel):
    api_key: str
    provider: str = "anthropic"


class ApiKeyStatusResponse(BaseModel):
    configured: bool
    key_hint: Optional[str] = None
    added_at: Optional[str] = None
    last_used: Optional[str] = None
    valid: bool = False
    subscription_status: str = "beta"


class ProviderKeyInfo(BaseModel):
    provider_id: str
    provider_name: str
    configured: bool
    key_hint: Optional[str] = None
    added_at: Optional[str] = None
    last_used: Optional[str] = None
    has_platform_key: bool = False
    has_platform_grant: bool = False
    grant_source: Optional[str] = None  # "user_grant" | "tier_grant"
    console_url: Optional[str] = None
    key_placeholder: Optional[str] = None


def _validate_anthropic_key(api_key: str):
    """Validate an Anthropic API key with a minimal test call."""
    if not api_key.startswith("sk-ant"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API key format. Anthropic keys start with 'sk-ant'"
        )
    try:
        test_client = anthropic.Anthropic(api_key=api_key)
        test_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}]
        )
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid API key. Please check your key and try again."
        )
    except anthropic.RateLimitError:
        pass  # Key is valid but rate limited
    except Exception as e:
        logger.error(f"Anthropic key validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not validate API key. Please try again."
        )


def _validate_openai_compat_key(api_key: str, provider_id: str):
    """Validate an OpenAI-compatible provider key with a minimal test call."""
    provider_config = PROVIDERS.get(provider_id)
    if not provider_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_id}"
        )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=provider_config["base_url"],
            timeout=15.0,
        )
        client.chat.completions.create(
            model=provider_config["default_model"],
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
    except OpenAIAuthError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid API key for {provider_config['name']}. Please check your key."
        )
    except Exception as e:
        error_str = str(e).lower()
        if "authentication" in error_str or "unauthorized" in error_str or "invalid api key" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid API key for {provider_config['name']}."
            )
        if "rate" in error_str and "limit" in error_str:
            pass  # Key is valid but rate limited
        else:
            logger.error(f"{provider_id} key validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not validate {provider_config['name']} key. Please try again."
            )


@router.post("/api-key")
async def set_api_key(
    request: ApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Set or update a provider API key.

    The key is validated with a test API call, then encrypted and stored.
    Only the encrypted version is saved - we never store or log the full key.
    """
    api_key = request.api_key.strip()
    provider_id = request.provider.strip().lower()

    if provider_id not in PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_id}. Available: {', '.join(PROVIDERS.keys())}"
        )

    if not api_key or len(api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is too short."
        )

    # Check BYOK tier access
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])

    if not tier_config.get("byok_allowed", False):
        raise HTTPException(
            status_code=403,
            detail="BYOK (Bring Your Own Key) requires Adept tier ($30/mo) or higher."
        )

    byok_providers = tier_config.get("byok_providers")
    if byok_providers and provider_id not in byok_providers:
        allowed_str = ", ".join(p.title() for p in byok_providers)
        raise HTTPException(
            status_code=403,
            detail=f"Your Adept plan allows BYOK for: {allowed_str}. Upgrade to Opus ($100/mo) for all providers."
        )

    # Validate with provider-specific test call
    if provider_id == "anthropic":
        _validate_anthropic_key(api_key)
    else:
        _validate_openai_compat_key(api_key, provider_id)

    # Encrypt and store
    encrypted_key = encrypt_value(api_key, settings.secret_key)
    key_hint = mask_api_key(api_key)

    if not user.settings:
        user.settings = {}
    if "api_keys" not in user.settings:
        user.settings["api_keys"] = {}

    user.settings["api_keys"][provider_id] = {
        "encrypted_key": encrypted_key,
        "key_hint": key_hint,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "valid": True,
    }

    flag_modified(user, "settings")
    await db.commit()

    provider_name = PROVIDERS[provider_id]["name"]
    logger.info(f"API key configured for user {user.id}, provider: {provider_id}")

    return {
        "status": "configured",
        "provider": provider_id,
        "key_hint": key_hint,
        "message": f"{provider_name} API key saved successfully."
    }


@router.delete("/api-key/{provider}")
async def remove_api_key(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a provider API key."""
    provider_id = provider.strip().lower()
    if user.settings and "api_keys" in user.settings:
        user.settings["api_keys"].pop(provider_id, None)
        flag_modified(user, "settings")
        await db.commit()

    provider_name = PROVIDERS.get(provider_id, {}).get("name", provider_id)
    return {"status": "removed", "message": f"{provider_name} API key removed."}


@router.get("/api-key/status")
async def get_api_key_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get API key status for all providers.

    Returns per-provider info: configured, key hint, platform key availability,
    and platform grant status.
    """
    from app.services.provider_access import has_user_platform_grant, has_tier_platform_grant

    settings_data = user.settings or {}
    api_keys = settings_data.get("api_keys", {})

    # Get user tier for tier-level grant checks
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"

    providers = {}
    for provider_id, provider_config in PROVIDERS.items():
        user_key = api_keys.get(provider_id, {})
        has_platform_key = bool(os.getenv(provider_config["key_env"]))

        info = ProviderKeyInfo(
            provider_id=provider_id,
            provider_name=provider_config["name"],
            configured=bool(user_key.get("encrypted_key")),
            key_hint=user_key.get("key_hint"),
            added_at=user_key.get("added_at"),
            last_used=user_key.get("last_used"),
            has_platform_key=has_platform_key,
            console_url=PROVIDER_CONSOLE_URLS.get(provider_id),
            key_placeholder=PROVIDER_KEY_HINTS.get(provider_id),
        )

        # Check platform grants (user-level first, then tier-level)
        user_grant = has_user_platform_grant(user, provider_id)
        if user_grant:
            info.has_platform_grant = True
            info.grant_source = "user_grant"
        else:
            tier_grant = await has_tier_platform_grant(tier, provider_id, db)
            if tier_grant:
                info.has_platform_grant = True
                info.grant_source = "tier_grant"

        providers[provider_id] = info

    return {"providers": {k: v.model_dump() for k, v in providers.items()}}


def get_user_api_key(user: User, provider: str = "anthropic") -> Optional[str]:
    """
    Get the decrypted API key for a user and provider.

    Used internally by the chat service.
    Returns None if no key is configured for that provider.
    """
    if not user or not user.settings:
        return None

    api_keys = user.settings.get("api_keys", {})
    provider_config = api_keys.get(provider, {})
    encrypted_key = provider_config.get("encrypted_key")

    if not encrypted_key:
        return None

    return decrypt_value(encrypted_key, settings.secret_key)
