"""
ApexAurum Cloud - Configuration

All settings loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # App
    app_name: str = "ApexAurum Cloud"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:3000,https://frontend-production-5402.up.railway.app"

    # Database (Railway provides postgresql://, we convert to asyncpg)
    database_url: str = "postgresql://apex:apex@localhost:5432/apex"

    @property
    def async_database_url(self) -> str:
        """Convert standard postgres URL to async format."""
        url = self.database_url
        # Handle both postgres:// and postgresql://
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3/MinIO
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = "apex-storage"

    # Anthropic
    anthropic_api_key: Optional[str] = None

    # Optional APIs
    voyage_api_key: Optional[str] = None
    suno_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Steel Browser
    steel_url: Optional[str] = None  # e.g., https://steel-browser-production-d237.up.railway.app

    # Stripe (Billing & Monetization)
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None

    # Stripe Price IDs (create these in Stripe Dashboard)
    stripe_price_seeker_monthly: Optional[str] = None   # $10/mo Seeker subscription
    stripe_price_adept_monthly: Optional[str] = None     # $30/mo Adept subscription
    stripe_price_opus_monthly: Optional[str] = None      # $100/mo Opus subscription
    stripe_price_azothic_monthly: Optional[str] = None   # $300/mo Azothic subscription
    stripe_price_credits_500: Optional[str] = None  # $5 for 500 credits
    stripe_price_credits_2500: Optional[str] = None  # $20 for 2500 credits

    # Feature pack prices (one-time payments)
    stripe_price_pack_spark: Optional[str] = None
    stripe_price_pack_flame: Optional[str] = None
    stripe_price_pack_inferno: Optional[str] = None

    # Email (stub - logs instead of sending)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_address: str = "noreply@apexaurum.cloud"
    smtp_from_name: str = "ApexAurum Cloud"

    # Embedding config (for vector search)
    # Providers: "local" (FastEmbed), "openai", or "voyage"
    embedding_provider: str = "local"  # Default to local for privacy
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # Local model (384 dims)
    # For OpenAI: "text-embedding-3-small" (1536 dims)
    # For local: "BAAI/bge-small-en-v1.5" (384), "BAAI/bge-base-en-v1.5" (768)
    embedding_dimensions: int = 384  # Match local model dimensions

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120  # 2 hours - built for long wanders
    refresh_token_expire_days: int = 30  # A full moon cycle

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # The Vault - File Storage
    # Tool execution
    tool_execution_timeout: int = 120  # seconds

    # Mount path is /data on Railway volume - use directly to avoid permission issues
    vault_path: str = "/data"
    max_file_size_bytes: int = 104_857_600  # 100MB
    default_quota_bytes: int = 5_368_709_120  # 5GB per user

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into list."""
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# ═══════════════════════════════════════════════════════════════════════════════
# TIER CONFIGURATION - Feature limits by subscription tier
# ═══════════════════════════════════════════════════════════════════════════════

TIER_LIMITS = {
    "free_trial": {
        "name": "Free Trial",
        "price_monthly": 0,
        "messages_per_month": 20,
        "models": ["claude-haiku-4-5-20251001"],
        "opus_messages_per_month": 0,
        "tools_enabled": False,
        "multi_provider": False,
        "byok_allowed": False,
        "api_access": False,
        "context_token_limit": 128_000,
        "council_sessions_per_month": 0,
        "council_max_rounds": 0,
        "suno_generations_per_month": 0,
        "jam_sessions_per_month": 0,
        "nursery_access": False,
        "pac_mode": False,
        "dev_mode": False,
        "vault_storage_mb": 0,
        "platform_grants": [],
        "trial_days": 7,
    },
    "seeker": {
        "name": "Seeker",
        "price_monthly": 10,
        "messages_per_month": 200,
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
        ],
        "opus_messages_per_month": 0,
        "tools_enabled": True,
        "multi_provider": False,
        "byok_allowed": False,
        "api_access": False,
        "context_token_limit": 128_000,
        "council_sessions_per_month": 3,
        "council_max_rounds": 10,
        "suno_generations_per_month": 10,
        "jam_sessions_per_month": 0,
        "nursery_access": False,
        "pac_mode": False,
        "dev_mode": False,
        "vault_storage_mb": 100,
        "platform_grants": [],
    },
    "adept": {
        "name": "Adept",
        "price_monthly": 30,
        "messages_per_month": 1000,
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-haiku-20240307",
        ],
        "opus_messages_per_month": 50,
        "tools_enabled": True,
        "multi_provider": True,
        "byok_allowed": True,
        "byok_providers": ["together", "groq", "deepseek", "qwen", "moonshot"],
        "api_access": False,
        "context_token_limit": None,
        "council_sessions_per_month": 10,
        "council_max_rounds": 50,
        "suno_generations_per_month": 50,
        "jam_sessions_per_month": 3,
        "nursery_access": "view_only",
        "pac_mode": "haiku",
        "dev_mode": False,
        "vault_storage_mb": 1024,
        "platform_grants": [],
    },
    "opus": {
        "name": "Opus",
        "price_monthly": 100,
        "messages_per_month": 5000,
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-haiku-20240307",
        ],
        "deprecated_models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
        ],
        "opus_messages_per_month": 500,
        "tools_enabled": True,
        "multi_provider": True,
        "byok_allowed": True,
        "api_access": True,
        "context_token_limit": None,
        "council_sessions_per_month": None,
        "council_max_rounds": 200,
        "suno_generations_per_month": 200,
        "jam_sessions_per_month": 20,
        "nursery_access": True,
        "pac_mode": True,
        "dev_mode": True,
        "vault_storage_mb": 5120,
        "platform_grants": [],
    },
    "azothic": {
        "name": "Azothic",
        "price_monthly": 300,
        "messages_per_month": 20000,
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-haiku-20240307",
        ],
        "deprecated_models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
        ],
        "opus_messages_per_month": 2000,
        "tools_enabled": True,
        "multi_provider": True,
        "byok_allowed": True,
        "api_access": True,
        "context_token_limit": None,
        "council_sessions_per_month": None,
        "council_max_rounds": None,
        "suno_generations_per_month": 500,
        "jam_sessions_per_month": None,
        "nursery_access": True,
        "nursery_training_credits": 5,
        "pac_mode": True,
        "dev_mode": True,
        "vault_storage_mb": 20480,
        "platform_grants": [],
    },
}

# Providers that support admin-controlled platform grants
GRANTABLE_PROVIDERS = ["together", "groq", "deepseek", "qwen", "moonshot", "suno"]

# Tier hierarchy for >= comparisons
TIER_HIERARCHY = {"free_trial": 0, "seeker": 1, "adept": 2, "opus": 3, "azothic": 4}

# Feature credit packs (replaces old cents-based credit system)
CREDIT_PACKS = {
    "spark": {
        "name": "Spark",
        "price_usd": 5.00,
        "chooseable": True,
        "options": {
            "opus_messages": 50,
            "suno_generations": 20,
            "training_jobs": 2,
        },
        "min_tier": "adept",
    },
    "flame": {
        "name": "Flame",
        "price_usd": 15.00,
        "chooseable": False,
        "contents": {
            "opus_messages": 150,
            "suno_generations": 50,
            "training_jobs": 5,
        },
        "min_tier": "adept",
    },
    "inferno": {
        "name": "Inferno",
        "price_usd": 40.00,
        "chooseable": False,
        "contents": {
            "opus_messages": 500,
            "suno_generations": 200,
            "training_jobs": 15,
        },
        "min_tier": "adept",
    },
}
