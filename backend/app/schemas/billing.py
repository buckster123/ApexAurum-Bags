"""
Billing Schemas - Request/Response models for billing endpoints.

ApexAurum monetization API schemas.
"""

from datetime import datetime
from typing import Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class SubscriptionCheckoutRequest(BaseModel):
    """Request to create a subscription checkout session."""
    tier: str = Field(..., description="Subscription tier: 'seeker', 'adept', 'opus', or 'azothic'")
    success_url: Optional[str] = Field(None, description="URL to redirect after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect if user cancels")


class SubscriptionCheckoutResponse(BaseModel):
    """Response with Stripe checkout session URL."""
    checkout_url: str = Field(..., description="Stripe Checkout URL to redirect user")
    session_id: str = Field(..., description="Stripe Checkout Session ID")


class SubscriptionStatus(BaseModel):
    """Current subscription status."""
    tier: str = Field(..., description="Current tier: 'free_trial', 'seeker', 'adept', 'opus', or 'azothic'")
    status: str = Field(..., description="Subscription status: 'active', 'past_due', 'canceled', 'trialing'")
    messages_used: int = Field(..., description="Messages used this period")
    messages_limit: Optional[int] = Field(None, description="Monthly message limit (None = unlimited)")
    current_period_start: Optional[datetime] = Field(None, description="Billing period start")
    current_period_end: Optional[datetime] = Field(None, description="Billing period end")
    cancel_at_period_end: bool = Field(False, description="Will cancel at end of period")


# ═══════════════════════════════════════════════════════════════════════════════
# CREDITS SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class CreditsCheckoutRequest(BaseModel):
    """Request to create a credits purchase checkout session."""
    pack: str = Field(..., description="Credit pack: 'small' ($5/500) or 'large' ($20/2500)")
    success_url: Optional[str] = Field(None, description="URL to redirect after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect if user cancels")


class CreditsCheckoutResponse(BaseModel):
    """Response with Stripe checkout session URL."""
    checkout_url: str = Field(..., description="Stripe Checkout URL to redirect user")
    session_id: str = Field(..., description="Stripe Checkout Session ID")


class CreditBalanceResponse(BaseModel):
    """Current credit balance."""
    balance_cents: int = Field(..., description="Current balance in cents")
    balance_usd: float = Field(..., description="Current balance in USD")
    total_purchased_cents: int = Field(..., description="Lifetime credits purchased")
    total_used_cents: int = Field(..., description="Lifetime credits used")


class CreditTransactionResponse(BaseModel):
    """Single credit transaction."""
    id: UUID
    amount_cents: int
    balance_after: int
    transaction_type: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CreditTransactionsResponse(BaseModel):
    """List of credit transactions."""
    transactions: List[CreditTransactionResponse]
    total: int


# ═══════════════════════════════════════════════════════════════════════════════
# BILLING STATUS (Combined Response)
# ═══════════════════════════════════════════════════════════════════════════════

class TierFeatures(BaseModel):
    """Features available for a tier."""
    models: List[str] = Field(..., description="Available model IDs")
    tools_enabled: bool = Field(..., description="Whether tools are available")
    multi_provider: bool = Field(..., description="Whether multi-provider LLMs are available")
    byok_allowed: bool = Field(..., description="Whether Bring Your Own Key is allowed")
    api_access: bool = Field(False, description="Whether API access is available")
    dev_mode: bool = False
    pac_mode: Any = False  # bool or str ("haiku")
    nursery_access: Any = False  # bool or str ("view_only")
    council_sessions_per_month: Optional[int] = None
    suno_generations_per_month: Optional[int] = None
    jam_sessions_per_month: Optional[int] = None
    opus_messages_per_month: int = 0
    byok_providers: Optional[list] = None


class BillingStatusResponse(BaseModel):
    """
    Complete billing status for the current user.

    Combines subscription, credits, and feature access into one response.
    Frontend should call this on load to determine UI state.
    """
    # Subscription info
    tier: str = Field(..., description="Current tier: 'free_trial', 'seeker', 'adept', 'opus', or 'azothic'")
    subscription_status: str = Field(..., description="Subscription status")
    messages_used: int = Field(..., description="Messages used this period")
    messages_limit: Optional[int] = Field(None, description="Monthly limit (None = unlimited)")
    messages_remaining: Optional[int] = Field(None, description="Messages remaining (None = unlimited)")
    current_period_end: Optional[datetime] = Field(None, description="When current period ends")
    cancel_at_period_end: bool = Field(False, description="Will cancel at end of period")
    trial_end: Optional[datetime] = None

    # Feature credits (purchased pack balances)
    feature_credits: Optional[dict] = Field(None, description="Feature credits: {opus_messages, suno_generations, training_jobs}")

    # Credit balance
    credit_balance_cents: int = Field(..., description="Credit balance in cents")
    credit_balance_usd: float = Field(..., description="Credit balance in USD")

    # Features (what the user can access based on tier)
    features: TierFeatures

    # Usage alerts
    at_limit: bool = Field(False, description="Whether user has hit message limit")
    near_limit: bool = Field(False, description="Whether user is >80% of limit")


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════════════════════════

class PortalSessionRequest(BaseModel):
    """Request to create a Stripe Customer Portal session."""
    return_url: Optional[str] = Field(None, description="URL to return to after portal")


class PortalSessionResponse(BaseModel):
    """Response with Customer Portal URL."""
    portal_url: str = Field(..., description="Stripe Customer Portal URL")


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

class PricingTier(BaseModel):
    """Pricing tier for display."""
    id: str = Field(..., description="Tier ID: 'seeker', 'adept', 'opus', 'azothic'")
    name: str = Field(..., description="Display name")
    tagline: str = Field(..., description="Short tagline")
    price_monthly: float = Field(..., description="Monthly price in USD")
    messages_per_month: Optional[int] = Field(None, description="Message limit (None = unlimited)")
    features: List[str] = Field(..., description="List of feature descriptions")
    popular: bool = Field(False, description="Whether to highlight as popular")


class CreditPack(BaseModel):
    """Credit pack for display."""
    id: str = Field(..., description="Pack ID: 'small', 'large'")
    name: str = Field(..., description="Display name")
    price_usd: float = Field(..., description="Price in USD")
    credits: int = Field(..., description="Number of credits")
    bonus_credits: int = Field(0, description="Bonus credits included")


class PricingResponse(BaseModel):
    """All pricing information for display."""
    tiers: List[PricingTier]
    credit_packs: List[CreditPack]  # Legacy, kept for backward compat
    feature_packs: List["FeatureCreditPack"] = []  # New feature credit packs


# ═══════════════════════════════════════════════════════════════════════════════
# COUPON SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class CouponCreateRequest(BaseModel):
    """Request to create a new coupon (admin only)."""
    code: str = Field(..., description="Unique coupon code (will be uppercased)", min_length=3, max_length=50)
    name: str = Field(..., description="Display name for the coupon", max_length=100)
    description: Optional[str] = Field(None, description="Description of the coupon")
    coupon_type: str = Field(..., description="Type: 'credit_bonus', 'tier_upgrade', 'subscription_discount'")
    value: int = Field(..., description="Credits for credit_bonus, days for tier_upgrade, % for discount", gt=0)
    tier: Optional[str] = Field(None, description="Target tier for tier_upgrade (pro, opus)")
    max_uses: Optional[int] = Field(None, description="Maximum total uses (None = unlimited)")
    max_uses_per_user: int = Field(1, description="Maximum uses per user")
    valid_until: Optional[datetime] = Field(None, description="Expiry date (None = never)")


class CouponResponse(BaseModel):
    """Coupon details."""
    id: UUID
    code: str
    name: str
    description: Optional[str]
    coupon_type: str
    value: int
    tier: Optional[str]
    max_uses: Optional[int]
    max_uses_per_user: int
    current_uses: int
    valid_from: datetime
    valid_until: Optional[datetime]
    is_active: bool
    is_valid: bool  # Computed: active, not expired, not maxed out
    created_at: datetime

    class Config:
        from_attributes = True


class CouponListResponse(BaseModel):
    """List of coupons."""
    coupons: List[CouponResponse]
    total: int


class CouponRedeemRequest(BaseModel):
    """Request to redeem a coupon."""
    code: str = Field(..., description="Coupon code to redeem")


class CouponRedeemResponse(BaseModel):
    """Response after redeeming a coupon."""
    success: bool
    message: str
    benefit_type: str
    benefit_value: int
    benefit_description: str  # Human-readable description of what was granted


class CouponCheckResponse(BaseModel):
    """Response when checking coupon validity."""
    valid: bool
    code: str
    name: Optional[str] = None
    coupon_type: Optional[str] = None
    value: Optional[int] = None
    tier: Optional[str] = None
    description: Optional[str] = None
    error: Optional[str] = None  # Why it's invalid, if applicable


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE PACK SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class PackCheckoutRequest(BaseModel):
    """Request to purchase a feature credit pack."""
    pack: str = Field(..., description="Pack ID: 'spark', 'flame', or 'inferno'")
    resource_type: Optional[str] = Field(None, description="For spark: 'opus_messages', 'suno_generations', or 'training_jobs'")
    success_url: Optional[str] = Field(None, description="URL to redirect after successful payment")
    cancel_url: Optional[str] = Field(None, description="URL to redirect if user cancels")


class PackCheckoutResponse(BaseModel):
    """Response with Stripe checkout session URL for pack purchase."""
    checkout_url: str = Field(..., description="Stripe Checkout URL to redirect user")
    session_id: str = Field(..., description="Stripe Checkout Session ID")


class FeatureCreditPack(BaseModel):
    """Feature credit pack for pricing display."""
    id: str = Field(..., description="Pack ID: 'spark', 'flame', 'inferno'")
    name: str = Field(..., description="Display name")
    price_usd: float = Field(..., description="Price in USD")
    chooseable: bool = Field(..., description="Whether user picks one resource (spark) vs gets all (flame/inferno)")
    options: Optional[dict] = Field(None, description="For chooseable packs: {resource_type: amount}")
    contents: Optional[dict] = Field(None, description="For bundle packs: {resource_type: amount}")
    min_tier: str = Field(..., description="Minimum tier required to purchase")

# Resolve forward reference now that FeatureCreditPack is defined
PricingResponse.model_rebuild()


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE DASHBOARD SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class UsageResourceDetail(BaseModel):
    """Per-resource usage detail for the usage dashboard."""
    counter_type: str = Field(..., description="Counter type identifier")
    display_name: str = Field(..., description="Human-readable resource name")
    current_count: int = Field(..., description="Usage count this period")
    tier_limit: Optional[int] = Field(None, description="Tier allowance (None = unlimited)")
    feature_credit_bonus: int = Field(0, description="Available feature credits for this resource")
    effective_limit: Optional[int] = Field(None, description="Tier limit + bonus (None = unlimited)")
    percentage_used: Optional[float] = Field(None, description="Usage percentage (None if unlimited)")
    status: str = Field("green", description="Color status: 'green', 'yellow', 'red'")


class UsageSummaryResponse(BaseModel):
    """Complete usage summary for the dashboard."""
    resources: List[UsageResourceDetail] = Field(..., description="Per-resource usage details")
    feature_credits: dict = Field(..., description="Available feature credits: {opus_messages, suno_generations, training_jobs}")
    period: str = Field(..., description="Billing period (YYYY-MM)")
    total_messages_used: int = Field(..., description="Total messages used this period")
    total_messages_limit: Optional[int] = Field(None, description="Monthly message limit (None = unlimited)")
