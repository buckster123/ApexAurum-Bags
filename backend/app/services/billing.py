"""
Billing Service - Usage tracking, limits enforcement, and Stripe integration.

Handles:
- Subscription limit checking
- Credit balance management
- Usage recording
- Stripe customer/subscription management
"""

import logging
from datetime import datetime, timedelta, timezone as tz
from typing import Optional, Tuple
from uuid import UUID, uuid4

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, TIER_LIMITS, TIER_HIERARCHY, CREDIT_PACKS
from app.models.billing import Subscription, CreditBalance, CreditTransaction, WebhookEvent
from app.models.user import User
from app.services.pricing import calculate_cost_cents, get_tier_for_model

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize Stripe
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key


class BillingService:
    """
    Service for billing operations.

    Provides methods for:
    - Checking if user can send messages
    - Checking if user can use specific models/features
    - Recording usage (subscription counter or credit deduction)
    - Managing subscriptions and credits
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_or_create_subscription(self, user_id: UUID) -> Subscription:
        """
        Get user's subscription, creating free tier if none exists.

        Also ensures Stripe customer exists.
        """
        result = await self.db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            return subscription

        # Get user for Stripe customer creation
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Create Stripe customer
        stripe_customer_id = await self._create_stripe_customer(user)

        # Create free trial subscription
        subscription = Subscription(
            id=uuid4(),
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            tier="free_trial",
            status="trialing",
            messages_used=0,
            messages_limit=TIER_LIMITS["free_trial"]["messages_per_month"],
            trial_end=datetime.now(tz.utc) + timedelta(days=7),
        )
        self.db.add(subscription)
        await self.db.flush()

        logger.info(f"Created free_trial subscription for user {user_id}")
        return subscription

    async def _create_stripe_customer(self, user: User) -> str:
        """Create Stripe customer for user."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured - cannot create customer")

        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.display_name or user.email.split("@")[0],
                metadata={"user_id": str(user.id)},
            )
            logger.info(f"Created Stripe customer {customer.id} for user {user.id}")
            return customer.id
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise ValueError(f"Failed to create Stripe customer: {e}")

    async def get_subscription_status(self, user_id: UUID) -> dict:
        """Get comprehensive subscription status for API response."""
        subscription = await self.get_or_create_subscription(user_id)
        credit_balance = await self.get_or_create_credit_balance(user_id)

        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])
        messages_limit = tier_config["messages_per_month"]

        # Calculate remaining messages
        messages_remaining = None
        if messages_limit is not None:
            messages_remaining = max(0, messages_limit - subscription.messages_used)

        # Check if at or near limit
        at_limit = messages_remaining == 0 if messages_remaining is not None else False
        near_limit = (
            messages_remaining is not None
            and messages_limit is not None
            and messages_remaining <= messages_limit * 0.2
        )

        # Per-model usage breakdown
        try:
            from app.services.usage import UsageService
            usage_service = UsageService(self.db)
            usage_counters = await usage_service.get_usage_summary(user_id)
        except Exception:
            usage_counters = {}

        # Feature credits (purchased pack balances)
        try:
            from app.services.usage import FeatureCreditService
            credit_svc = FeatureCreditService(self.db)
            feature_credits = await credit_svc.get_credit_summary(user_id)
        except Exception:
            feature_credits = {"opus_messages": 0, "suno_generations": 0, "training_jobs": 0}

        return {
            "tier": subscription.tier,
            "subscription_status": subscription.status,
            "messages_used": subscription.messages_used,
            "messages_limit": messages_limit,
            "messages_remaining": messages_remaining,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "trial_end": subscription.trial_end,
            "credit_balance_cents": credit_balance.balance_cents,
            "credit_balance_usd": credit_balance.balance_cents / 100,
            "features": {
                "models": tier_config["models"],
                "tools_enabled": tier_config["tools_enabled"],
                "multi_provider": tier_config["multi_provider"],
                "byok_allowed": tier_config["byok_allowed"],
                "api_access": tier_config.get("api_access", False),
                "dev_mode": tier_config.get("dev_mode", False),
                "pac_mode": tier_config.get("pac_mode", False),
                "nursery_access": tier_config.get("nursery_access", False),
                "council_sessions_per_month": tier_config.get("council_sessions_per_month"),
                "suno_generations_per_month": tier_config.get("suno_generations_per_month"),
                "jam_sessions_per_month": tier_config.get("jam_sessions_per_month"),
                "opus_messages_per_month": tier_config.get("opus_messages_per_month", 0),
                "byok_providers": tier_config.get("byok_providers"),
            },
            "at_limit": at_limit,
            "near_limit": near_limit,
            "usage_counters": usage_counters,
            "feature_credits": feature_credits,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # CREDIT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_or_create_credit_balance(self, user_id: UUID) -> CreditBalance:
        """Get user's credit balance, creating if none exists."""
        result = await self.db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user_id)
        )
        credit_balance = result.scalar_one_or_none()

        if credit_balance:
            return credit_balance

        # Create empty balance
        credit_balance = CreditBalance(
            id=uuid4(),
            user_id=user_id,
            balance_cents=0,
            total_purchased_cents=0,
            total_used_cents=0,
        )
        self.db.add(credit_balance)
        await self.db.flush()

        return credit_balance

    async def add_credits(
        self,
        user_id: UUID,
        amount_cents: int,
        transaction_type: str = "purchase",
        description: Optional[str] = None,
        stripe_payment_intent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CreditBalance:
        """
        Add credits to user's balance.

        Creates transaction record for audit trail.
        """
        credit_balance = await self.get_or_create_credit_balance(user_id)

        # Update balance
        credit_balance.balance_cents += amount_cents
        if transaction_type == "purchase":
            credit_balance.total_purchased_cents += amount_cents

        # Create transaction record
        transaction = CreditTransaction(
            id=uuid4(),
            user_id=user_id,
            amount_cents=amount_cents,
            balance_after=credit_balance.balance_cents,
            transaction_type=transaction_type,
            description=description or f"Added {amount_cents} credits",
            stripe_payment_intent_id=stripe_payment_intent_id,
            extra_data=metadata or {},
        )
        self.db.add(transaction)
        await self.db.flush()

        logger.info(f"Added {amount_cents}c credits to user {user_id}, balance now {credit_balance.balance_cents}c")
        return credit_balance

    async def deduct_credits(
        self,
        user_id: UUID,
        amount_cents: int,
        description: Optional[str] = None,
        message_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Deduct credits from user's balance.

        Returns True if successful, False if insufficient funds.
        """
        credit_balance = await self.get_or_create_credit_balance(user_id)

        if credit_balance.balance_cents < amount_cents:
            return False

        # Update balance
        credit_balance.balance_cents -= amount_cents
        credit_balance.total_used_cents += amount_cents

        # Create transaction record
        transaction = CreditTransaction(
            id=uuid4(),
            user_id=user_id,
            amount_cents=-amount_cents,  # Negative for deduction
            balance_after=credit_balance.balance_cents,
            transaction_type="usage",
            description=description or f"Deducted {amount_cents} credits",
            message_id=message_id,
            extra_data=metadata or {},
        )
        self.db.add(transaction)
        await self.db.flush()

        logger.debug(f"Deducted {amount_cents}c from user {user_id}, balance now {credit_balance.balance_cents}c")
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # USAGE CHECKS & ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def can_send_message(self, user_id: UUID) -> Tuple[bool, str]:
        """
        Check if user can send a message.

        Logic:
        1. Check subscription limit first
        2. If at limit, check credit balance
        3. Return (allowed, reason)
        """
        subscription = await self.get_or_create_subscription(user_id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])

        # Check subscription status
        if subscription.status not in ("active", "trialing"):
            return False, "subscription_inactive"

        # Check trial expiry
        if subscription.tier == "free_trial" and subscription.trial_end:
            if datetime.now(tz.utc) > subscription.trial_end:
                return False, "trial_expired"

        # Check subscription limit
        messages_limit = tier_config["messages_per_month"]
        if messages_limit is None:
            # Unlimited (opus tier)
            return True, "subscription"

        if subscription.messages_used < messages_limit:
            return True, "subscription"

        # At subscription limit, check credits
        credit_balance = await self.get_or_create_credit_balance(user_id)
        if credit_balance.balance_cents > 0:
            return True, "credits"

        return False, "limit_reached"

    async def can_use_model(self, user_id: UUID, model: str) -> bool:
        """Check if user's tier allows the specified model."""
        subscription = await self.get_or_create_subscription(user_id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])

        allowed_models = tier_config["models"]

        # Check exact match first
        if model in allowed_models:
            return True

        # Check model tier requirement
        required_tier = get_tier_for_model(model)
        tier_hierarchy = {"free_trial": 0, "seeker": 1, "adept": 2, "opus": 3, "azothic": 4}

        user_tier_level = tier_hierarchy.get(subscription.tier, 0)
        required_tier_level = tier_hierarchy.get(required_tier, 0)

        return user_tier_level >= required_tier_level

    async def can_use_tools(self, user_id: UUID) -> bool:
        """Check if user's tier allows tool usage."""
        subscription = await self.get_or_create_subscription(user_id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])
        return tier_config["tools_enabled"]

    async def can_use_multi_provider(self, user_id: UUID) -> bool:
        """Check if user's tier allows multi-provider LLMs."""
        subscription = await self.get_or_create_subscription(user_id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])
        return tier_config["multi_provider"]

    # ═══════════════════════════════════════════════════════════════════════════
    # USAGE RECORDING
    # ═══════════════════════════════════════════════════════════════════════════

    async def record_message_usage(
        self,
        user_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        message_id: Optional[UUID] = None,
    ) -> dict:
        """
        Record message usage, either incrementing subscription counter or deducting credits.

        Returns usage info for the message.
        """
        subscription = await self.get_or_create_subscription(user_id)
        tier_config = TIER_LIMITS.get(subscription.tier, TIER_LIMITS["free_trial"])
        messages_limit = tier_config["messages_per_month"]

        # Calculate cost
        cost_cents = calculate_cost_cents(provider, model, input_tokens, output_tokens)

        usage_info = {
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": cost_cents,
            "billing_type": None,
        }

        # Check if should use subscription or credits
        if messages_limit is None or subscription.messages_used < messages_limit:
            # Use subscription allowance
            subscription.messages_used += 1
            usage_info["billing_type"] = "subscription"
            usage_info["messages_remaining"] = (
                None if messages_limit is None
                else messages_limit - subscription.messages_used
            )
        else:
            # Use credits
            success = await self.deduct_credits(
                user_id=user_id,
                amount_cents=cost_cents,
                description=f"{model}: {input_tokens}in/{output_tokens}out tokens",
                message_id=message_id,
                metadata={
                    "provider": provider,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )
            if not success:
                logger.warning(f"Failed to deduct credits for user {user_id}")

            credit_balance = await self.get_or_create_credit_balance(user_id)
            usage_info["billing_type"] = "credits"
            usage_info["credits_remaining"] = credit_balance.balance_cents

        # Per-model usage tracking via UsageCounter (parallel to subscription counter)
        try:
            from app.services.usage import UsageService, classify_model_family
            usage_service = UsageService(self.db)
            counter_type = classify_model_family(provider, model)
            await usage_service.increment_usage(user_id, counter_type)
        except Exception as e:
            logger.warning(f"Usage counter increment failed (non-fatal): {e}")

        await self.db.flush()
        return usage_info

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTION PERIOD RESET
    # ═══════════════════════════════════════════════════════════════════════════

    async def reset_subscription_usage(self, user_id: UUID) -> None:
        """Reset subscription message counter (called when new billing period starts)."""
        result = await self.db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.messages_used = 0
            await self.db.flush()
            logger.info(f"Reset usage counter for user {user_id}")

    # ═══════════════════════════════════════════════════════════════════════════
    # WEBHOOK IDEMPOTENCY
    # ═══════════════════════════════════════════════════════════════════════════

    async def is_webhook_processed(self, event_id: str) -> bool:
        """Check if webhook event has already been processed."""
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_webhook_processed(
        self,
        event_id: str,
        event_type: str,
        payload: Optional[dict] = None,
    ) -> None:
        """Mark webhook event as processed."""
        event = WebhookEvent(
            id=event_id,
            event_type=event_type,
            processed_at=datetime.utcnow(),
            payload=payload,
        )
        self.db.add(event)
        await self.db.flush()

    # ═══════════════════════════════════════════════════════════════════════════
    # STRIPE CHECKOUT
    # ═══════════════════════════════════════════════════════════════════════════

    async def _ensure_valid_stripe_customer(self, subscription, user: User) -> str:
        """Ensure subscription has a valid Stripe customer ID, creating one if needed."""
        customer_id = subscription.stripe_customer_id

        # Check if customer ID looks invalid (our old error placeholders)
        if not customer_id or customer_id.startswith("cus_error_") or customer_id.startswith("cus_local_"):
            logger.warning(f"Invalid customer ID '{customer_id}' for user {user.id}, creating new one")
            # Create new Stripe customer
            new_customer_id = await self._create_stripe_customer(user)
            subscription.stripe_customer_id = new_customer_id
            await self.db.flush()
            return new_customer_id

        # Verify customer exists in Stripe
        try:
            stripe.Customer.retrieve(customer_id)
            return customer_id
        except stripe.InvalidRequestError as e:
            if "No such customer" in str(e):
                logger.warning(f"Customer {customer_id} not found in Stripe, creating new one")
                new_customer_id = await self._create_stripe_customer(user)
                subscription.stripe_customer_id = new_customer_id
                await self.db.flush()
                return new_customer_id
            raise

    async def create_subscription_checkout(
        self,
        user_id: UUID,
        tier: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create Stripe Checkout session for subscription."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured")

        subscription = await self.get_or_create_subscription(user_id)

        # Get user for customer validation
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Ensure we have a valid Stripe customer
        customer_id = await self._ensure_valid_stripe_customer(subscription, user)

        # Get price ID for tier
        tier_price_map = {
            "seeker": settings.stripe_price_seeker_monthly,
            "adept": settings.stripe_price_adept_monthly,
            "opus": settings.stripe_price_opus_monthly,
            "azothic": settings.stripe_price_azothic_monthly,
        }
        price_id = tier_price_map.get(tier)
        if not price_id:
            raise ValueError(f"Price not configured for tier: {tier}")

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                automatic_tax={"enabled": True},
                customer_update={"address": "auto"},  # Save billing address for tax calculation
                billing_address_collection="required",
                metadata={"user_id": str(user_id), "tier": tier},
            )
            return {
                "checkout_url": session.url,
                "session_id": session.id,
            }
        except stripe.StripeError as e:
            logger.error(f"Stripe checkout error: {e}")
            raise

    async def create_credits_checkout(
        self,
        user_id: UUID,
        pack: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create Stripe Checkout session for credit purchase."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured")

        subscription = await self.get_or_create_subscription(user_id)

        # Get user for customer validation
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Ensure we have a valid Stripe customer
        customer_id = await self._ensure_valid_stripe_customer(subscription, user)

        # Get price ID for pack
        price_id = None
        if pack == "small":
            price_id = settings.stripe_price_credits_500
        elif pack == "large":
            price_id = settings.stripe_price_credits_2500
        else:
            raise ValueError(f"Invalid pack: {pack}")

        if not price_id:
            raise ValueError(f"Price not configured for pack: {pack}")

        pack_config = CREDIT_PACKS[pack]
        total_credits = pack_config["credits"] + pack_config["bonus"]

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                mode="payment",
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                automatic_tax={"enabled": True},
                customer_update={"address": "auto"},  # Save billing address for tax calculation
                billing_address_collection="required",
                metadata={
                    "user_id": str(user_id),
                    "pack": pack,
                    "credits": str(total_credits),
                },
            )
            return {
                "checkout_url": session.url,
                "session_id": session.id,
            }
        except stripe.StripeError as e:
            logger.error(f"Stripe checkout error: {e}")
            raise

    async def create_pack_checkout(
        self,
        user_id: UUID,
        pack_id: str,
        resource_type: Optional[str],
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """
        Create a Stripe Checkout session for a feature credit pack purchase.

        Args:
            user_id: User making the purchase.
            pack_id: "spark", "flame", or "inferno"
            resource_type: For spark: which resource to get. None for bundles.
            success_url: URL to redirect after payment.
            cancel_url: URL to redirect on cancel.

        Returns:
            Dict with checkout_url and session_id.
        """
        pack = CREDIT_PACKS.get(pack_id)
        if not pack:
            raise ValueError(f"Unknown pack: {pack_id}")

        # Validate tier requirement
        subscription = await self.get_or_create_subscription(user_id)
        tier = subscription.tier
        min_tier = pack.get("min_tier", "adept")
        if TIER_HIERARCHY.get(tier, 0) < TIER_HIERARCHY.get(min_tier, 2):
            raise ValueError(f"Feature packs require {min_tier} tier or higher. Current tier: {tier}")

        # Validate resource_type for chooseable packs (spark)
        if pack.get("chooseable"):
            if not resource_type or resource_type not in pack.get("options", {}):
                raise ValueError(f"Spark pack requires resource_type: {list(pack.get('options', {}).keys())}")

        # Get Stripe price ID
        price_map = {
            "spark": settings.stripe_price_pack_spark,
            "flame": settings.stripe_price_pack_flame,
            "inferno": settings.stripe_price_pack_inferno,
        }
        price_id = price_map.get(pack_id)
        if not price_id:
            raise ValueError(f"Stripe price not configured for pack: {pack_id}")

        # Ensure valid Stripe customer
        user = await self.db.get(User, user_id)
        customer_id = await self._ensure_valid_stripe_customer(subscription, user)

        # Create Stripe checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={
                "user_id": str(user_id),
                "pack": pack_id,
                "resource_type": resource_type or "",
                "type": "feature_pack",
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )

        logger.info(f"Created pack checkout for user {user_id}: pack={pack_id} resource={resource_type}")

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    async def create_portal_session(
        self,
        user_id: UUID,
        return_url: str,
    ) -> dict:
        """Create Stripe Customer Portal session."""
        if not settings.stripe_secret_key:
            raise ValueError("Stripe not configured")

        subscription = await self.get_or_create_subscription(user_id)

        # Get user for customer validation
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Ensure we have a valid Stripe customer
        customer_id = await self._ensure_valid_stripe_customer(subscription, user)

        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return {"portal_url": session.url}
        except stripe.StripeError as e:
            logger.error(f"Stripe portal error: {e}")
            raise
