"""
Usage Service - Granular usage tracking engine.

Provides atomic increment via PostgreSQL upsert, limit checking,
and usage summary queries. Designed to work alongside the existing
BillingService for fine-grained per-resource tracking.

Usage:
    from app.services.usage import UsageService, COUNTER_MESSAGES_HAIKU

    service = UsageService(db)
    new_count = await service.increment_usage(user_id, COUNTER_MESSAGES_HAIKU)
    allowed, current, limit = await service.check_usage_limit(user_id, COUNTER_MESSAGES_HAIKU, 1000)
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.usage import UsageCounter
from app.models.feature_credit import FeatureCreditBalance
from app.config import CREDIT_PACKS

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# COUNTER TYPE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

COUNTER_MESSAGES_HAIKU = "messages_haiku"
COUNTER_MESSAGES_SONNET = "messages_sonnet"
COUNTER_MESSAGES_OPUS = "messages_opus"
COUNTER_MESSAGES_OTHER = "messages_other"
COUNTER_SUNO_GENERATIONS = "suno_generations"
COUNTER_COUNCIL_SESSIONS = "council_sessions"
COUNTER_JAM_SESSIONS = "jam_sessions"
COUNTER_NURSERY_TRAINING = "nursery_training_jobs"

# Map counter types to feature credit resource columns
COUNTER_TO_RESOURCE = {
    COUNTER_MESSAGES_OPUS: "opus_messages",
    COUNTER_SUNO_GENERATIONS: "suno_generations",
    COUNTER_NURSERY_TRAINING: "training_jobs",
}

# Maps counter types to TIER_LIMITS keys for threshold warnings
COUNTER_TO_LIMIT_KEY = {
    "messages_haiku": "messages_per_month",
    "messages_sonnet": "messages_per_month",
    "messages_opus": "opus_messages_per_month",
    "suno_generations": "suno_generations_per_month",
    "council_sessions": "council_sessions_per_month",
    "jam_sessions": "jam_sessions_per_month",
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_current_period() -> str:
    """Return current billing period as YYYY-MM string."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def classify_model_family(provider: str, model: str) -> str:
    """
    Classify a provider/model combination into a counter type.

    Only Anthropic models are classified by family; all other providers
    fall through to COUNTER_MESSAGES_OTHER.
    """
    if provider != "anthropic":
        return COUNTER_MESSAGES_OTHER

    model_lower = model.lower()
    if "opus" in model_lower:
        return COUNTER_MESSAGES_OPUS
    if "sonnet" in model_lower:
        return COUNTER_MESSAGES_SONNET
    if "haiku" in model_lower:
        return COUNTER_MESSAGES_HAIKU

    return COUNTER_MESSAGES_OTHER


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class UsageService:
    """
    Core usage tracking engine.

    Provides atomic counter increments via PostgreSQL upsert,
    limit checking, and usage summary queries.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def increment_usage(
        self,
        user_id: UUID,
        counter_type: str,
        amount: int = 1,
        limit_snapshot: Optional[int] = None,
    ) -> int:
        """
        Atomically increment a usage counter via PostgreSQL upsert.

        If no row exists for (user_id, counter_type, period), one is inserted
        with count=amount. If a row already exists, count is incremented by
        amount and updated_at is refreshed.

        Args:
            user_id: The user whose usage to track.
            counter_type: One of the COUNTER_* constants.
            amount: How much to increment (default 1).
            limit_snapshot: Optional informational snapshot of the limit
                           at the time the counter was created.

        Returns:
            The new count after increment.
        """
        period = get_current_period()

        stmt = pg_insert(UsageCounter).values(
            id=uuid4(),
            user_id=user_id,
            counter_type=counter_type,
            period=period,
            count=amount,
            limit_snapshot=limit_snapshot,
        )

        stmt = stmt.on_conflict_do_update(
            constraint='uq_usage_counter_user_type_period',
            set_=dict(
                count=UsageCounter.count + amount,
                updated_at=datetime.now(timezone.utc),
            ),
        )

        stmt = stmt.returning(UsageCounter.count)

        result = await self.db.execute(stmt)
        new_count = result.scalar_one()

        logger.debug(
            f"Usage increment: user={user_id} type={counter_type} "
            f"period={period} amount={amount} new_count={new_count}"
        )

        # Check for usage warning thresholds (non-fatal)
        try:
            await self._check_usage_thresholds(user_id, counter_type, new_count)
        except Exception as e:
            logger.warning(f"Usage warning trigger failed (non-fatal): {e}")

        return new_count

    async def check_usage_limit(
        self,
        user_id: UUID,
        counter_type: str,
        limit: Optional[int],
    ) -> tuple[bool, int, Optional[int]]:
        """
        Check whether a user is within their usage limit.

        If user is at their tier limit but has purchased feature credits
        for this resource, access is still allowed (credits will be
        deducted after the action succeeds).

        Args:
            user_id: The user to check.
            counter_type: One of the COUNTER_* constants.
            limit: The maximum allowed count, or None for unlimited.

        Returns:
            Tuple of (allowed, current_count, limit):
            - allowed: True if usage is permitted.
            - current_count: Current usage count this period.
            - limit: The limit passed in (None means unlimited).
        """
        current = await self.get_current_count(user_id, counter_type)

        if limit is None:
            return (True, current, None)

        if current < limit:
            return (True, current, limit)

        # At tier limit -- check feature credits as overflow
        resource_type = COUNTER_TO_RESOURCE.get(counter_type)
        if resource_type:
            try:
                credit_svc = FeatureCreditService(self.db)
                available = await credit_svc.get_available_credits(user_id, resource_type)
                if available > 0:
                    logger.debug(
                        f"User {user_id} at tier limit for {counter_type} "
                        f"but has {available} feature credits for {resource_type}"
                    )
                    return (True, current, limit)
            except Exception as e:
                logger.warning(f"Feature credit check failed (non-fatal): {e}")

        return (False, current, limit)

    async def get_current_count(
        self,
        user_id: UUID,
        counter_type: str,
    ) -> int:
        """
        Get the current period's count for a specific counter.

        Returns 0 if no counter row exists for this period.
        """
        period = get_current_period()

        result = await self.db.execute(
            select(UsageCounter.count).where(
                UsageCounter.user_id == user_id,
                UsageCounter.counter_type == counter_type,
                UsageCounter.period == period,
            )
        )

        return result.scalar_one_or_none() or 0

    async def get_usage_summary(
        self,
        user_id: UUID,
        period: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Get all usage counters for a user in a given period.

        Args:
            user_id: The user to query.
            period: Billing period as YYYY-MM string. Defaults to current period.

        Returns:
            Dict mapping counter_type to count, e.g.:
            {"messages_haiku": 42, "suno_generations": 3}
        """
        if period is None:
            period = get_current_period()

        result = await self.db.execute(
            select(UsageCounter.counter_type, UsageCounter.count).where(
                UsageCounter.user_id == user_id,
                UsageCounter.period == period,
            )
        )

        return {row.counter_type: row.count for row in result.all()}

    async def deduct_feature_credit_if_over_limit(
        self,
        user_id: UUID,
        counter_type: str,
        tier_limit: Optional[int],
    ) -> bool:
        """
        Deduct a feature credit if user has exceeded their tier limit.

        Called AFTER an action succeeds. If the user's usage count is
        over their tier limit, one feature credit is deducted.

        Args:
            user_id: The user.
            counter_type: One of the COUNTER_* constants.
            tier_limit: The tier's limit for this counter (None = unlimited).

        Returns:
            True if a feature credit was deducted, False otherwise.
        """
        if tier_limit is None:
            return False

        current = await self.get_current_count(user_id, counter_type)
        if current <= tier_limit:
            return False  # Still within tier allowance

        resource_type = COUNTER_TO_RESOURCE.get(counter_type)
        if not resource_type:
            return False

        try:
            credit_svc = FeatureCreditService(self.db)
            return await credit_svc.deduct_credit(user_id, resource_type)
        except Exception as e:
            logger.warning(f"Feature credit deduction failed (non-fatal): {e}")
            return False

    async def _check_usage_thresholds(
        self,
        user_id: UUID,
        counter_type: str,
        current_count: int,
    ) -> None:
        """
        Check if usage has crossed 80% or 100% thresholds and trigger email warnings.
        Only fires on exact threshold crossing (prev < threshold <= current).
        Non-fatal: failures are logged but don't affect the calling operation.
        """
        limit_key = COUNTER_TO_LIMIT_KEY.get(counter_type)
        if not limit_key:
            return

        try:
            from app.models.billing import Subscription
            from app.config import TIER_LIMITS
            from sqlalchemy import select

            # Look up user's tier
            result = await self.db.execute(
                select(Subscription.tier).where(Subscription.user_id == user_id)
            )
            tier = result.scalar_one_or_none() or "free_trial"
            tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])

            limit = tier_config.get(limit_key)
            if not limit or limit <= 0:
                return  # Unlimited or not configured

            percent = (current_count * 100) // limit
            prev_percent = ((current_count - 1) * 100) // limit

            # Determine which thresholds were just crossed
            thresholds = []
            if percent >= 100 and prev_percent < 100:
                thresholds.append(100)
            elif percent >= 80 and prev_percent < 80:
                thresholds.append(80)

            if not thresholds:
                return

            # Fetch user email
            from app.models.user import User
            user_result = await self.db.execute(
                select(User.email, User.display_name).where(User.id == user_id)
            )
            user_row = user_result.one_or_none()
            if not user_row:
                return

            from app.services.email import send_usage_warning

            for threshold in thresholds:
                await send_usage_warning(
                    user_email=user_row.email,
                    user_display_name=user_row.display_name,
                    resource=counter_type,
                    percent=threshold,
                    current=current_count,
                    limit=limit,
                )
        except Exception as e:
            logger.warning(f"Usage threshold check failed (non-fatal): {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE CREDIT SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class FeatureCreditService:
    """
    Service for managing purchased feature credits (Spark/Flame/Inferno packs).

    Feature credits are stored as per-purchase rows with remaining balances.
    Deduction uses FIFO (oldest purchase first). Credits expire based on
    expires_at timestamp.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_available_credits(
        self,
        user_id: UUID,
        resource_type: str,
    ) -> int:
        """
        Sum remaining credits for a resource across all active purchases.

        Args:
            user_id: The user.
            resource_type: "opus_messages", "suno_generations", or "training_jobs"

        Returns:
            Total available credits for the resource.
        """
        column = getattr(FeatureCreditBalance, resource_type, None)
        if column is None:
            return 0

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(func.coalesce(func.sum(column), 0)).where(
                and_(
                    FeatureCreditBalance.user_id == user_id,
                    FeatureCreditBalance.is_expired == False,
                    FeatureCreditBalance.expires_at > now,
                    column > 0,
                )
            )
        )

        return result.scalar_one()

    async def deduct_credit(
        self,
        user_id: UUID,
        resource_type: str,
        amount: int = 1,
    ) -> bool:
        """
        Deduct credits using FIFO (oldest purchase first).

        Args:
            user_id: The user.
            resource_type: "opus_messages", "suno_generations", or "training_jobs"
            amount: How many to deduct (default 1).

        Returns:
            True if sufficient credits existed and were deducted.
        """
        column = getattr(FeatureCreditBalance, resource_type, None)
        if column is None:
            return False

        now = datetime.now(timezone.utc)
        remaining = amount

        # Get active credit rows ordered oldest first (FIFO)
        result = await self.db.execute(
            select(FeatureCreditBalance).where(
                and_(
                    FeatureCreditBalance.user_id == user_id,
                    FeatureCreditBalance.is_expired == False,
                    FeatureCreditBalance.expires_at > now,
                    column > 0,
                )
            ).order_by(FeatureCreditBalance.purchased_at.asc())
        )

        rows = result.scalars().all()

        for row in rows:
            current_val = getattr(row, resource_type)
            if current_val <= 0:
                continue

            deduct = min(remaining, current_val)
            setattr(row, resource_type, current_val - deduct)
            remaining -= deduct

            logger.debug(
                f"Deducted {deduct} {resource_type} from purchase {row.id} "
                f"(remaining in purchase: {current_val - deduct})"
            )

            if remaining <= 0:
                break

        if remaining > 0:
            logger.warning(
                f"Insufficient feature credits for user {user_id}: "
                f"needed {amount} {resource_type}, short by {remaining}"
            )
            return False

        await self.db.flush()
        return True

    async def add_pack_credits(
        self,
        user_id: UUID,
        pack_id: str,
        resource_type: Optional[str] = None,
        stripe_payment_intent_id: Optional[str] = None,
    ) -> FeatureCreditBalance:
        """
        Add credits from a pack purchase.

        Creates a new FeatureCreditBalance row with appropriate expiry.

        Args:
            user_id: The purchasing user.
            pack_id: "spark", "flame", or "inferno"
            resource_type: For spark: which resource ("opus_messages", "suno_generations", "training_jobs")
            stripe_payment_intent_id: Stripe payment reference.

        Returns:
            The created FeatureCreditBalance row.
        """
        pack = CREDIT_PACKS.get(pack_id)
        if not pack:
            raise ValueError(f"Unknown pack: {pack_id}")

        # Calculate expiry: end of current month + 1 full calendar month
        now = datetime.now(timezone.utc)
        # Move to first of next month, then add another month
        if now.month == 12:
            next_month_start = now.replace(year=now.year + 1, month=2, day=1, hour=0, minute=0, second=0, microsecond=0)
        elif now.month == 11:
            next_month_start = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_start = now.replace(month=now.month + 2, day=1, hour=0, minute=0, second=0, microsecond=0)
        expires_at = next_month_start

        # Determine credit amounts
        opus_msgs = 0
        suno_gens = 0
        train_jobs = 0

        if pack.get("chooseable"):
            # Spark: user picks one resource
            if not resource_type or resource_type not in pack["options"]:
                raise ValueError(f"Spark pack requires resource_type from: {list(pack['options'].keys())}")
            amount = pack["options"][resource_type]
            if resource_type == "opus_messages":
                opus_msgs = amount
            elif resource_type == "suno_generations":
                suno_gens = amount
            elif resource_type == "training_jobs":
                train_jobs = amount
        else:
            # Flame/Inferno: bundle of all three
            contents = pack.get("contents", {})
            opus_msgs = contents.get("opus_messages", 0)
            suno_gens = contents.get("suno_generations", 0)
            train_jobs = contents.get("training_jobs", 0)

        balance = FeatureCreditBalance(
            user_id=user_id,
            pack_id=pack_id,
            resource_type=resource_type,
            opus_messages=opus_msgs,
            suno_generations=suno_gens,
            training_jobs=train_jobs,
            purchased_at=now,
            expires_at=expires_at,
            stripe_payment_intent_id=stripe_payment_intent_id,
        )

        self.db.add(balance)
        await self.db.flush()

        logger.info(
            f"Added feature credits for user {user_id}: "
            f"pack={pack_id} opus={opus_msgs} suno={suno_gens} training={train_jobs} "
            f"expires={expires_at.isoformat()}"
        )

        return balance

    async def get_credit_summary(
        self,
        user_id: UUID,
    ) -> dict:
        """
        Get total available feature credits across all active purchases.

        Returns:
            Dict with keys: opus_messages, suno_generations, training_jobs
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(FeatureCreditBalance.opus_messages), 0),
                func.coalesce(func.sum(FeatureCreditBalance.suno_generations), 0),
                func.coalesce(func.sum(FeatureCreditBalance.training_jobs), 0),
            ).where(
                and_(
                    FeatureCreditBalance.user_id == user_id,
                    FeatureCreditBalance.is_expired == False,
                    FeatureCreditBalance.expires_at > now,
                )
            )
        )

        row = result.one()
        return {
            "opus_messages": row[0],
            "suno_generations": row[1],
            "training_jobs": row[2],
        }
