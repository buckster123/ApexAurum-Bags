"""
Billing Endpoints - Subscriptions, Credits, and Stripe Checkout.

ApexAurum monetization API.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.billing import CreditTransaction
from app.auth.deps import get_current_user
from app.config import get_settings, TIER_LIMITS, TIER_HIERARCHY, CREDIT_PACKS
from app.services.billing import BillingService
from app.schemas.billing import (
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    CreditsCheckoutRequest,
    CreditsCheckoutResponse,
    CreditTransactionResponse,
    CreditTransactionsResponse,
    BillingStatusResponse,
    TierFeatures,
    PortalSessionRequest,
    PortalSessionResponse,
    PricingTier,
    CreditPack,
    PricingResponse,
    CouponCreateRequest,
    CouponResponse,
    CouponListResponse,
    CouponRedeemRequest,
    CouponRedeemResponse,
    CouponCheckResponse,
    PackCheckoutRequest,
    PackCheckoutResponse,
    FeatureCreditPack,
    UsageSummaryResponse,
    UsageResourceDetail,
)
from app.services.usage import UsageService, FeatureCreditService, get_current_period
from app.models.billing import Coupon, CouponRedemption, CreditBalance

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# BILLING STATUS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current billing status for the authenticated user.

    Returns:
    - Current subscription tier and status
    - Message usage and limits
    - Credit balance
    - Available features for the tier

    Call this on app load to determine UI state.
    """
    billing_service = BillingService(db)
    status_data = await billing_service.get_subscription_status(user.id)

    return BillingStatusResponse(
        tier=status_data["tier"],
        subscription_status=status_data["subscription_status"],
        messages_used=status_data["messages_used"],
        messages_limit=status_data["messages_limit"],
        messages_remaining=status_data["messages_remaining"],
        current_period_end=status_data["current_period_end"],
        cancel_at_period_end=status_data["cancel_at_period_end"],
        trial_end=status_data.get("trial_end"),
        feature_credits=status_data.get("feature_credits"),
        credit_balance_cents=status_data["credit_balance_cents"],
        credit_balance_usd=status_data["credit_balance_usd"],
        features=TierFeatures(**status_data["features"]),
        at_limit=status_data["at_limit"],
        near_limit=status_data["near_limit"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION CHECKOUT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/checkout/subscription", response_model=SubscriptionCheckoutResponse)
async def create_subscription_checkout(
    request: SubscriptionCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Checkout session for subscription upgrade.

    Args:
        tier: 'pro' or 'opus'

    Returns:
        checkout_url: Redirect user to this URL to complete payment
        session_id: Stripe session ID for reference

    After successful payment, Stripe webhook will update the subscription.
    """
    if request.tier not in ("seeker", "adept", "opus", "azothic"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier. Must be 'seeker', 'adept', 'opus', or 'azothic'."
        )

    # Build URLs - prefer HTTPS production URL over localhost
    base_url = "http://localhost:3000"
    for origin in settings.allowed_origins_list:
        if origin.startswith("https://"):
            base_url = origin
            break
    success_url = request.success_url or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = request.cancel_url or f"{base_url}/billing"

    try:
        billing_service = BillingService(db)
        result = await billing_service.create_subscription_checkout(
            user_id=user.id,
            tier=request.tier,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        await db.commit()
        return SubscriptionCheckoutResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CREDITS CHECKOUT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/checkout/credits", response_model=CreditsCheckoutResponse, deprecated=True)
async def create_credits_checkout(
    request: CreditsCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Checkout session for credit purchase.

    DEPRECATED: Use POST /checkout/pack for feature credit packs instead.
    Kept for backward compatibility with older frontend versions.

    Args:
        pack: 'small' ($5/500 credits) or 'large' ($20/2500 credits with 25% bonus)

    Returns:
        checkout_url: Redirect user to this URL to complete payment
        session_id: Stripe session ID for reference

    After successful payment, Stripe webhook will add credits to balance.
    """
    if request.pack not in ("small", "large"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pack. Must be 'small' or 'large'."
        )

    # Build URLs - prefer HTTPS production URL over localhost
    base_url = "http://localhost:3000"
    for origin in settings.allowed_origins_list:
        if origin.startswith("https://"):
            base_url = origin
            break
    success_url = request.success_url or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = request.cancel_url or f"{base_url}/billing"

    try:
        billing_service = BillingService(db)
        result = await billing_service.create_credits_checkout(
            user_id=user.id,
            pack=request.pack,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        await db.commit()
        return CreditsCheckoutResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE PACK CHECKOUT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/checkout/pack", response_model=PackCheckoutResponse)
async def create_pack_checkout(
    request: PackCheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe checkout session for a feature credit pack."""
    if request.pack not in ("spark", "flame", "inferno"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pack. Must be 'spark', 'flame', or 'inferno'.",
        )

    if request.pack == "spark" and not request.resource_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spark pack requires resource_type: 'opus_messages', 'suno_generations', or 'training_jobs'.",
        )

    if request.resource_type and request.resource_type not in ("opus_messages", "suno_generations", "training_jobs"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid resource_type. Must be 'opus_messages', 'suno_generations', or 'training_jobs'.",
        )

    try:
        # Build URLs
        frontend_url = "https://frontend-production-5402.up.railway.app"
        success_url = request.success_url or f"{frontend_url}/billing?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{frontend_url}/billing"

        billing_service = BillingService(db)
        result = await billing_service.create_pack_checkout(
            user_id=user.id,
            pack_id=request.pack,
            resource_type=request.resource_type,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        return PackCheckoutResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Pack checkout error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create checkout session.")


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER PORTAL
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/portal", response_model=PortalSessionResponse)
async def create_portal_session(
    request: PortalSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Customer Portal session.

    The portal allows users to:
    - Update payment method
    - View invoices
    - Cancel subscription
    - Update billing details

    Returns:
        portal_url: Redirect user to this URL to access the portal
    """
    # Build return URL
    base_url = settings.allowed_origins_list[0] if settings.allowed_origins_list else "http://localhost:3000"
    return_url = request.return_url or f"{base_url}/billing"

    try:
        billing_service = BillingService(db)
        result = await billing_service.create_portal_session(
            user_id=user.id,
            return_url=return_url,
        )
        return PortalSessionResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Portal error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create portal session"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CREDIT TRANSACTIONS (Audit Log)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/transactions", response_model=CreditTransactionsResponse)
async def get_credit_transactions(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get credit transaction history for the authenticated user.

    Returns paginated list of transactions including:
    - Purchases
    - Usage deductions
    - Bonuses/refunds
    """
    from sqlalchemy import func

    # Get transactions
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    transactions = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(func.count(CreditTransaction.id))
        .where(CreditTransaction.user_id == user.id)
    )
    total = count_result.scalar() or 0

    return CreditTransactionsResponse(
        transactions=[
            CreditTransactionResponse(
                id=t.id,
                amount_cents=t.amount_cents,
                balance_after=t.balance_after,
                transaction_type=t.transaction_type,
                description=t.description,
                created_at=t.created_at,
            )
            for t in transactions
        ],
        total=total,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive usage summary with per-resource breakdown."""
    from app.models.billing import Subscription

    # Get tier
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscription = result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])

    # Get usage counters
    usage_svc = UsageService(db)
    counters = await usage_svc.get_usage_summary(user.id)

    # Get feature credits
    credit_svc = FeatureCreditService(db)
    feature_credits = await credit_svc.get_credit_summary(user.id)

    # Build per-resource details
    resource_defs = [
        ("messages_opus", "Opus Messages", "opus_messages_per_month", "opus_messages"),
        ("council_sessions", "Council Sessions", "council_sessions_per_month", None),
        ("suno_generations", "Suno Generations", "suno_generations_per_month", "suno_generations"),
        ("jam_sessions", "Jam Sessions", "jam_sessions_per_month", None),
        ("messages_haiku", "Haiku Messages", None, None),
        ("messages_sonnet", "Sonnet Messages", None, None),
        ("messages_other", "Other Messages", None, None),
    ]

    resources = []
    for counter_type, display_name, limit_key, credit_key in resource_defs:
        current = counters.get(counter_type, 0)
        tier_limit = tier_config.get(limit_key) if limit_key else None
        bonus = feature_credits.get(credit_key, 0) if credit_key else 0

        if tier_limit is not None:
            effective = tier_limit + bonus
            pct = round((current / effective) * 100, 1) if effective > 0 else 100.0
            if pct >= 90:
                color = "red"
            elif pct >= 60:
                color = "yellow"
            else:
                color = "green"
        else:
            effective = None
            pct = None
            color = "green"

        resources.append(UsageResourceDetail(
            counter_type=counter_type,
            display_name=display_name,
            current_count=current,
            tier_limit=tier_limit,
            feature_credit_bonus=bonus,
            effective_limit=effective,
            percentage_used=pct,
            status=color,
        ))

    # Total messages
    total_used = sum(counters.get(k, 0) for k in ["messages_haiku", "messages_sonnet", "messages_opus", "messages_other"])
    total_limit = tier_config.get("messages_per_month")

    return UsageSummaryResponse(
        resources=resources,
        feature_credits=feature_credits,
        period=get_current_period(),
        total_messages_used=total_used,
        total_messages_limit=total_limit,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PRICING DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/pricing", response_model=PricingResponse)
async def get_pricing():
    """
    Get all pricing information for display.

    Returns tier details and credit pack options.
    No authentication required - this is public info.
    """
    tiers = [
        PricingTier(
            id="seeker",
            name="Seeker",
            tagline="Begin your journey",
            price_monthly=10,
            messages_per_month=200,
            features=[
                "200 messages per month",
                "Haiku + Sonnet models",
                "All 68 tools",
                "3 Council sessions/month",
                "10 Suno generations/month",
                "128K context limit",
            ],
            popular=False,
        ),
        PricingTier(
            id="adept",
            name="Adept",
            tagline="Master the Athanor",
            price_monthly=30,
            messages_per_month=1000,
            features=[
                "1,000 messages per month",
                "All models + 50 Opus/month",
                "10 Council sessions, 50 Suno/month",
                "3 Jam sessions/month",
                "BYOK (OSS providers)",
                "Nursery Data Garden (browse)",
                "Full context + PAC Mode (Haiku)",
            ],
            popular=True,
        ),
        PricingTier(
            id="opus",
            name="Opus",
            tagline="Unlimited mastery",
            price_monthly=100,
            messages_per_month=5000,
            features=[
                "5,000 messages + 500 Opus/month",
                "All models + Legacy",
                "Unlimited Council, 200 Suno/month",
                "Full Nursery access (training)",
                "Dev Mode + PAC Mode",
                "BYOK (all providers)",
                "5GB vault storage",
            ],
            popular=False,
        ),
        PricingTier(
            id="azothic",
            name="Azothic",
            tagline="The Philosopher's Stone",
            price_monthly=300,
            messages_per_month=20000,
            features=[
                "20,000 messages + 2,000 Opus/month",
                "Everything in Opus tier",
                "Unlimited Council, Jam, 500 Suno/month",
                "5 training jobs/month included",
                "20GB vault storage",
                "Priority routing",
            ],
            popular=False,
        ),
    ]

    credit_packs = [
        CreditPack(
            id="small",
            name="Starter Pack",
            price_usd=5.00,
            credits=500,
            bonus_credits=0,
        ),
        CreditPack(
            id="large",
            name="Power Pack",
            price_usd=20.00,
            credits=2000,
            bonus_credits=500,  # 25% bonus
        ),
    ]

    feature_packs = [
        FeatureCreditPack(
            id="spark",
            name="Spark",
            price_usd=5.00,
            chooseable=True,
            options={
                "opus_messages": {"amount": 50, "label": "50 Opus Messages"},
                "suno_generations": {"amount": 20, "label": "20 Suno Generations"},
                "training_jobs": {"amount": 2, "label": "2 Training Jobs"},
            },
            min_tier="adept",
        ),
        FeatureCreditPack(
            id="flame",
            name="Flame",
            price_usd=15.00,
            chooseable=False,
            contents={
                "opus_messages": 150,
                "suno_generations": 50,
                "training_jobs": 5,
            },
            min_tier="adept",
        ),
        FeatureCreditPack(
            id="inferno",
            name="Inferno",
            price_usd=40.00,
            chooseable=False,
            contents={
                "opus_messages": 500,
                "suno_generations": 200,
                "training_jobs": 15,
            },
            min_tier="adept",
        ),
    ]

    return PricingResponse(tiers=tiers, credit_packs=credit_packs, feature_packs=feature_packs)


# ═══════════════════════════════════════════════════════════════════════════════
# COUPONS - User Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/coupon/{code}", response_model=CouponCheckResponse)
async def check_coupon(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a coupon code is valid for the current user.

    Validates:
    - Coupon exists and is active
    - Not expired
    - Not maxed out (total uses)
    - User hasn't exceeded per-user limit
    """
    code_upper = code.strip().upper()

    # Find coupon
    result = await db.execute(
        select(Coupon).where(Coupon.code == code_upper)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        return CouponCheckResponse(valid=False, code=code_upper, error="Coupon not found")

    if not coupon.is_active:
        return CouponCheckResponse(valid=False, code=code_upper, error="Coupon is no longer active")

    if not coupon.is_valid():
        return CouponCheckResponse(valid=False, code=code_upper, error="Coupon has expired or reached maximum uses")

    # Check user's redemption count for this coupon
    result = await db.execute(
        select(CouponRedemption)
        .where(CouponRedemption.coupon_id == coupon.id)
        .where(CouponRedemption.user_id == user.id)
    )
    user_redemptions = len(result.scalars().all())

    if user_redemptions >= coupon.max_uses_per_user:
        return CouponCheckResponse(valid=False, code=code_upper, error="You have already redeemed this coupon")

    # Coupon is valid for this user
    return CouponCheckResponse(
        valid=True,
        code=coupon.code,
        name=coupon.name,
        coupon_type=coupon.coupon_type,
        value=coupon.value,
        tier=coupon.tier,
        description=coupon.description,
    )


@router.post("/coupon/redeem", response_model=CouponRedeemResponse)
async def redeem_coupon(
    request: CouponRedeemRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Redeem a coupon code.

    Applies the coupon benefit to the user's account:
    - credit_bonus: Adds credits to balance
    - tier_upgrade: Grants temporary tier access
    """
    code_upper = request.code.strip().upper()

    # Find coupon
    result = await db.execute(
        select(Coupon).where(Coupon.code == code_upper)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    if not coupon.is_active or not coupon.is_valid():
        raise HTTPException(status_code=400, detail="Coupon is not valid")

    # Check user's redemption count
    result = await db.execute(
        select(CouponRedemption)
        .where(CouponRedemption.coupon_id == coupon.id)
        .where(CouponRedemption.user_id == user.id)
    )
    user_redemptions = len(result.scalars().all())

    if user_redemptions >= coupon.max_uses_per_user:
        raise HTTPException(status_code=400, detail="You have already redeemed this coupon")

    # Apply the benefit based on coupon type
    benefit_description = ""
    benefit_details = {}

    if coupon.coupon_type == "credit_bonus":
        # Add credits to user's balance
        billing_service = BillingService(db)
        await billing_service.add_credits(
            user_id=user.id,
            amount_cents=coupon.value,
            description=f"Coupon: {coupon.name} ({coupon.code})",
            transaction_type="bonus",
        )
        benefit_description = f"Added {coupon.value} credits to your balance"
        benefit_details = {"credits_added": coupon.value}

    elif coupon.coupon_type == "tier_upgrade":
        # Grant temporary tier access
        from datetime import datetime, timedelta, timezone

        # Calculate expiry date
        expiry_date = datetime.now(timezone.utc) + timedelta(days=coupon.value)
        target_tier = coupon.tier or "opus"

        # Update user's subscription tier (or create temporary override)
        # For now, we'll update the subscription directly
        # In a more sophisticated system, you'd have a separate "tier_overrides" table
        from app.models.billing import Subscription

        result = await db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            # Store original tier if not already upgraded
            original_tier = subscription.tier
            subscription.tier = target_tier
            # Set the period end to the coupon expiry
            if not subscription.current_period_end or subscription.current_period_end < expiry_date:
                subscription.current_period_end = expiry_date

            benefit_details = {
                "tier": target_tier,
                "days": coupon.value,
                "expires": expiry_date.isoformat(),
                "original_tier": original_tier,
            }
        else:
            # Create a new subscription for the user
            from uuid import uuid4
            new_sub = Subscription(
                user_id=user.id,
                stripe_customer_id=f"coupon_{uuid4().hex[:8]}",  # Placeholder
                tier=target_tier,
                status="active",
                current_period_end=expiry_date,
                messages_limit=TIER_LIMITS.get(target_tier, {}).get("messages_per_month"),
            )
            db.add(new_sub)
            benefit_details = {
                "tier": target_tier,
                "days": coupon.value,
                "expires": expiry_date.isoformat(),
            }

        benefit_description = f"Upgraded to {target_tier.title()} tier for {coupon.value} days"

    elif coupon.coupon_type == "subscription_discount":
        # For subscription discounts, we'd integrate with Stripe coupons
        # For now, just record it - actual discount applied via Stripe
        benefit_description = f"{coupon.value}% off your next subscription payment"
        benefit_details = {"discount_percent": coupon.value}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown coupon type: {coupon.coupon_type}")

    # Record the redemption
    redemption = CouponRedemption(
        coupon_id=coupon.id,
        user_id=user.id,
        benefit_type=coupon.coupon_type,
        benefit_value=coupon.value,
        benefit_details=benefit_details,
    )
    db.add(redemption)

    # Increment coupon usage
    coupon.current_uses += 1

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="You have already redeemed this coupon")

    logger.info(f"Coupon {coupon.code} redeemed by user {user.id}: {benefit_description}")

    return CouponRedeemResponse(
        success=True,
        message=f"Coupon '{coupon.name}' redeemed successfully!",
        benefit_type=coupon.coupon_type,
        benefit_value=coupon.value,
        benefit_description=benefit_description,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# COUPONS - Admin Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/admin/coupons", response_model=CouponResponse)
async def create_coupon(
    request: CouponCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new coupon (admin only).

    Requires the user to have is_admin=True.
    """
    # Check admin status
    if not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")

    code_upper = request.code.strip().upper()

    # Check if code already exists
    result = await db.execute(
        select(Coupon).where(Coupon.code == code_upper)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Coupon code '{code_upper}' already exists")

    # Validate coupon type
    valid_types = ["credit_bonus", "tier_upgrade", "subscription_discount"]
    if request.coupon_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid coupon type. Must be one of: {valid_types}")

    # Validate tier for tier_upgrade
    if request.coupon_type == "tier_upgrade":
        if not request.tier or request.tier not in ["pro", "opus"]:
            raise HTTPException(status_code=400, detail="tier_upgrade coupons require tier: 'pro' or 'opus'")

    # Create coupon
    coupon = Coupon(
        code=code_upper,
        name=request.name,
        description=request.description,
        coupon_type=request.coupon_type,
        value=request.value,
        tier=request.tier,
        max_uses=request.max_uses,
        max_uses_per_user=request.max_uses_per_user,
        valid_until=request.valid_until,
        created_by=user.id,
    )
    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)

    logger.info(f"Coupon created by {user.id}: {coupon.code} ({coupon.coupon_type})")

    return CouponResponse(
        id=coupon.id,
        code=coupon.code,
        name=coupon.name,
        description=coupon.description,
        coupon_type=coupon.coupon_type,
        value=coupon.value,
        tier=coupon.tier,
        max_uses=coupon.max_uses,
        max_uses_per_user=coupon.max_uses_per_user,
        current_uses=coupon.current_uses,
        valid_from=coupon.valid_from,
        valid_until=coupon.valid_until,
        is_active=coupon.is_active,
        is_valid=coupon.is_valid(),
        created_at=coupon.created_at,
    )


@router.get("/admin/coupons", response_model=CouponListResponse)
async def list_coupons(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(False, description="Include deactivated coupons"),
):
    """
    List all coupons (admin only).
    """
    if not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")

    query = select(Coupon).order_by(Coupon.created_at.desc())
    if not include_inactive:
        query = query.where(Coupon.is_active == True)

    result = await db.execute(query)
    coupons = result.scalars().all()

    return CouponListResponse(
        coupons=[
            CouponResponse(
                id=c.id,
                code=c.code,
                name=c.name,
                description=c.description,
                coupon_type=c.coupon_type,
                value=c.value,
                tier=c.tier,
                max_uses=c.max_uses,
                max_uses_per_user=c.max_uses_per_user,
                current_uses=c.current_uses,
                valid_from=c.valid_from,
                valid_until=c.valid_until,
                is_active=c.is_active,
                is_valid=c.is_valid(),
                created_at=c.created_at,
            )
            for c in coupons
        ],
        total=len(coupons),
    )


@router.delete("/admin/coupons/{code}")
async def deactivate_coupon(
    code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a coupon (admin only).

    Does not delete the coupon - just marks it as inactive.
    """
    if not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Admin access required")

    code_upper = code.strip().upper()

    result = await db.execute(
        select(Coupon).where(Coupon.code == code_upper)
    )
    coupon = result.scalar_one_or_none()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    coupon.is_active = False
    await db.commit()

    logger.info(f"Coupon deactivated by {user.id}: {coupon.code}")

    return {"status": "deactivated", "code": coupon.code}
