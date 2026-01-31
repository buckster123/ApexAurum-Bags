"""
Platform Provider Grants - Unified Access Resolution

Replaces ad-hoc key resolution across chat, nursery, and tools.

Resolution priority:
1. User BYOK key (always preferred -- user pays directly)
2. User platform grant (admin granted this specific user)
3. Tier platform grant (admin granted this user's tier)
4. Static tier defaults (from TIER_LIMITS config)
5. Anthropic default (always available via platform key)
6. Unavailable
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, TIER_LIMITS

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory cache for tier-level grants (single-process deployment)
_cached_tier_grants: dict = {}
_cache_loaded = False


# ═══════════════════════════════════════════════════════════════════════════════
# Cache Management
# ═══════════════════════════════════════════════════════════════════════════════


async def load_tier_grants(db: AsyncSession) -> dict:
    """Load tier-level platform grants from system_settings table."""
    global _cached_tier_grants, _cache_loaded
    from app.models.system import SystemSettings

    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "platform_tier_grants")
    )
    row = result.scalar_one_or_none()

    if row and row.value:
        _cached_tier_grants = row.value
    else:
        _cached_tier_grants = {}

    _cache_loaded = True
    return _cached_tier_grants


def invalidate_tier_grants_cache():
    """Called after admin updates tier grants."""
    global _cache_loaded
    _cache_loaded = False


# ═══════════════════════════════════════════════════════════════════════════════
# Grant Checks
# ═══════════════════════════════════════════════════════════════════════════════


def _check_grant_expiry(grant_value) -> bool:
    """Check if a grant is active (not expired)."""
    if grant_value is True:
        return True
    if isinstance(grant_value, dict):
        expires_at = grant_value.get("expires_at")
        if not expires_at:
            return True
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < expiry
        except (ValueError, TypeError):
            return True  # Malformed = treat as non-expiring
    return bool(grant_value)


def has_user_platform_grant(user, provider: str) -> bool:
    """Check if user has a direct (per-user) platform grant."""
    if not user or not user.settings:
        return False
    grants = user.settings.get("platform_grants", {})
    grant = grants.get(provider)
    if not grant:
        return False
    return _check_grant_expiry(grant)


async def has_tier_platform_grant(
    tier: str, provider: str, db: Optional[AsyncSession] = None
) -> bool:
    """Check if a tier has a platform grant for a provider."""
    global _cached_tier_grants, _cache_loaded

    # Try DB override first (runtime admin config)
    if _cache_loaded:
        tier_grants = _cached_tier_grants.get(tier, {})
        grant = tier_grants.get(provider)
        if grant is not None:
            return _check_grant_expiry(grant)
    elif db:
        await load_tier_grants(db)
        tier_grants = _cached_tier_grants.get(tier, {})
        grant = tier_grants.get(provider)
        if grant is not None:
            return _check_grant_expiry(grant)

    # Fall back to static TIER_LIMITS defaults
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS.get("free_trial", {}))
    static_grants = tier_config.get("platform_grants", [])
    return provider in static_grants


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Resolution
# ═══════════════════════════════════════════════════════════════════════════════


async def resolve_provider_access(
    user,
    provider: str,
    tier: str,
    db: Optional[AsyncSession] = None,
) -> dict:
    """
    Unified provider access resolution.

    Returns:
        {
            "allowed": bool,
            "source": "byok" | "user_grant" | "tier_grant" |
                      "platform_default" | "unavailable",
            "api_key": str | None,
                # Decrypted BYOK key for source=byok.
                # None for platform sources (callers let env resolve).
        }
    """
    from app.api.v1.user import get_user_api_key
    from app.services.llm_provider import PROVIDERS

    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        return {"allowed": False, "source": "unavailable", "api_key": None}

    key_env = provider_config.get("key_env", "")

    # 1. User BYOK key (always preferred)
    user_key = get_user_api_key(user, provider)
    if user_key:
        return {"allowed": True, "source": "byok", "api_key": user_key}

    # 2. User-level platform grant
    if has_user_platform_grant(user, provider):
        if os.getenv(key_env):
            return {"allowed": True, "source": "user_grant", "api_key": None}
        logger.warning(
            f"User {getattr(user, 'id', '?')} has grant for {provider} "
            f"but platform env var {key_env} is not set"
        )

    # 3. Tier-level platform grant (DB override or static config)
    if await has_tier_platform_grant(tier, provider, db):
        if os.getenv(key_env):
            return {"allowed": True, "source": "tier_grant", "api_key": None}

    # 4. Anthropic is always available via platform key
    if provider == "anthropic" and settings.anthropic_api_key:
        return {
            "allowed": True,
            "source": "platform_default",
            "api_key": settings.anthropic_api_key,
        }

    # 5. Any provider with platform env var + tier allows multi_provider
    env_key = os.getenv(key_env)
    if env_key:
        tier_config = TIER_LIMITS.get(tier, TIER_LIMITS.get("free_trial", {}))
        if tier_config.get("multi_provider") or provider == "anthropic":
            return {"allowed": True, "source": "platform_default", "api_key": None}

    return {"allowed": False, "source": "unavailable", "api_key": None}
