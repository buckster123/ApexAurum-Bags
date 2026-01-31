"""
Webhook Endpoints - Handle external service webhooks.

Currently supports:
- Stripe webhooks for billing events
"""

import logging
from datetime import datetime
from uuid import UUID

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_context
from app.config import get_settings, TIER_LIMITS, CREDIT_PACKS
from app.models.billing import Subscription
from app.services.billing import BillingService
from app.services.usage import FeatureCreditService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# STRIPE WEBHOOK
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.

    Events processed:
    - checkout.session.completed: Add credits or activate subscription
    - customer.subscription.created: Create/update subscription record
    - customer.subscription.updated: Sync tier, status, period
    - customer.subscription.deleted: Downgrade to free tier
    - invoice.paid: Confirm subscription active, reset usage
    - invoice.payment_failed: Mark subscription as past_due

    All events are idempotent - duplicate processing is safe.
    """
    # Get raw payload for signature verification
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header"
        )

    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
    except ValueError:
        logger.error("Invalid payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.SignatureVerificationError:
        logger.error("Invalid signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Stripe webhook: {event_type} ({event_id})")

    # Process event with database session
    async with get_db_context() as db:
        billing_service = BillingService(db)

        # Check idempotency
        if await billing_service.is_webhook_processed(event_id):
            logger.info(f"Event {event_id} already processed, skipping")
            return {"status": "already_processed"}

        try:
            # Route to handler
            if event_type == "checkout.session.completed":
                await handle_checkout_completed(data, billing_service, db)

            elif event_type == "customer.subscription.created":
                await handle_subscription_created(data, billing_service, db)

            elif event_type == "customer.subscription.updated":
                await handle_subscription_updated(data, billing_service, db)

            elif event_type == "customer.subscription.deleted":
                await handle_subscription_deleted(data, billing_service, db)

            elif event_type == "invoice.paid":
                await handle_invoice_paid(data, billing_service, db)

            elif event_type == "invoice.payment_failed":
                await handle_invoice_payment_failed(data, billing_service, db)

            else:
                logger.debug(f"Unhandled event type: {event_type}")

            # Mark as processed
            await billing_service.mark_webhook_processed(
                event_id=event_id,
                event_type=event_type,
                payload=data,
            )

            await db.commit()

        except Exception as e:
            logger.error(f"Webhook processing error: {e}")
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Webhook processing failed: {str(e)}"
            )

    return {"status": "processed"}


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_checkout_completed(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle checkout.session.completed event.

    Triggered when user completes a checkout session.
    For subscriptions: Subscription events will follow.
    For credits: Add credits to balance immediately.
    """
    mode = data.get("mode")
    metadata = data.get("metadata", {})
    user_id_str = metadata.get("user_id")

    if not user_id_str:
        logger.warning("Checkout completed without user_id in metadata")
        return

    user_id = UUID(user_id_str)

    if mode == "payment":
        pack = metadata.get("pack")
        pack_type = metadata.get("type", "")

        # NEW: Feature credit packs (Spark/Flame/Inferno)
        if pack in ("spark", "flame", "inferno") or pack_type == "feature_pack":
            resource_type = metadata.get("resource_type") or None
            if resource_type == "":
                resource_type = None

            credit_svc = FeatureCreditService(db)
            await credit_svc.add_pack_credits(
                user_id=user_id,
                pack_id=pack,
                resource_type=resource_type,
                stripe_payment_intent_id=data.get("payment_intent"),
            )
            await db.commit()
            logger.info(f"Feature pack credits added for user {user_id}: pack={pack} resource={resource_type}")

        # LEGACY: Old cents-based credits (small/large packs)
        elif pack in ("small", "large"):
            credits_str = metadata.get("credits")
            if credits_str:
                credits = int(credits_str)
                pack_config = CREDIT_PACKS.get(pack, {})

                await billing.add_credits(
                    user_id=user_id,
                    amount_cents=credits,
                    transaction_type="purchase",
                    description=f"Credit purchase: {pack_config.get('price_usd', 0):.2f} USD for {credits} credits",
                    stripe_payment_intent_id=data.get("payment_intent"),
                    metadata={"pack": pack},
                )

                logger.info(f"Added {credits} credits for user {user_id} (pack: {pack})")

    elif mode == "subscription":
        # Subscription checkout - handled by subscription.created event
        logger.info(f"Subscription checkout completed for user {user_id}")


async def handle_subscription_created(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle customer.subscription.created event.

    Creates or updates subscription record with Stripe data.
    """
    customer_id = data.get("customer")
    subscription_id = data.get("id")

    # Find subscription by Stripe customer ID
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for Stripe customer {customer_id}")
        return

    # Get tier from price ID
    price_id = None
    items = data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")

    tier = _get_tier_from_price(price_id)

    # Update subscription
    subscription.stripe_subscription_id = subscription_id
    subscription.stripe_price_id = price_id
    subscription.tier = tier
    subscription.status = data.get("status", "active")
    subscription.messages_limit = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])["messages_per_month"]

    # Set billing period
    if data.get("current_period_start"):
        subscription.current_period_start = datetime.fromtimestamp(data["current_period_start"])
    if data.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(data["current_period_end"])

    subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)

    logger.info(f"Subscription created for user {subscription.user_id}: {tier}")


async def handle_subscription_updated(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle customer.subscription.updated event.

    Syncs subscription status, tier, and billing period.
    """
    subscription_id = data.get("id")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for Stripe subscription {subscription_id}")
        return

    # Get tier from price
    price_id = None
    items = data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")

    if price_id:
        tier = _get_tier_from_price(price_id)
        subscription.tier = tier
        subscription.stripe_price_id = price_id
        subscription.messages_limit = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])["messages_per_month"]

    # Update status
    subscription.status = data.get("status", subscription.status)

    # Update billing period
    if data.get("current_period_start"):
        subscription.current_period_start = datetime.fromtimestamp(data["current_period_start"])
    if data.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(data["current_period_end"])

    subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)

    logger.info(f"Subscription updated for user {subscription.user_id}: {subscription.tier} ({subscription.status})")


async def handle_subscription_deleted(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle customer.subscription.deleted event.

    Downgrades user to free tier.
    """
    subscription_id = data.get("id")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for Stripe subscription {subscription_id}")
        return

    # Downgrade to free_trial
    subscription.tier = "free_trial"
    subscription.status = "canceled"
    subscription.stripe_subscription_id = None
    subscription.stripe_price_id = None
    subscription.messages_limit = TIER_LIMITS["free_trial"]["messages_per_month"]
    subscription.messages_used = 0  # Reset usage

    logger.info(f"Subscription canceled for user {subscription.user_id}, downgraded to free_trial")


async def handle_invoice_paid(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle invoice.paid event.

    Confirms subscription is active and resets usage counter for new period.
    """
    subscription_id = data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return

    # Confirm active
    subscription.status = "active"

    # Reset usage counter for new billing period
    subscription.messages_used = 0

    # Update period dates from invoice
    if data.get("period_start"):
        subscription.current_period_start = datetime.fromtimestamp(data["period_start"])
    if data.get("period_end"):
        subscription.current_period_end = datetime.fromtimestamp(data["period_end"])

    logger.info(f"Invoice paid for user {subscription.user_id}, usage reset")


async def handle_invoice_payment_failed(data: dict, billing: BillingService, db: AsyncSession):
    """
    Handle invoice.payment_failed event.

    Marks subscription as past_due.
    """
    subscription_id = data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return

    subscription.status = "past_due"

    logger.warning(f"Payment failed for user {subscription.user_id}, marked as past_due")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_tier_from_price(price_id: str) -> str:
    """Determine subscription tier from Stripe price ID."""
    if not price_id:
        return "free_trial"

    if price_id == settings.stripe_price_seeker_monthly:
        return "seeker"
    elif price_id == settings.stripe_price_adept_monthly:
        return "adept"
    elif price_id == settings.stripe_price_opus_monthly:
        return "opus"
    elif price_id == settings.stripe_price_azothic_monthly:
        return "azothic"

    # Fallback: check price ID naming convention
    price_lower = price_id.lower()
    if "azothic" in price_lower:
        return "azothic"
    elif "opus" in price_lower:
        return "opus"
    elif "adept" in price_lower:
        return "adept"
    elif "seeker" in price_lower:
        return "seeker"

    return "seeker"  # Default paid tier, not free_trial
