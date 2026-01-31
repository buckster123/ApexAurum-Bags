"""
Billing Models - Subscriptions, Credits, and Transactions

ApexAurum monetization infrastructure with Stripe integration.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Integer, Boolean, Float, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class Subscription(Base):
    """
    User subscription synced with Stripe.

    Tiers:
    - free_trial: 20 messages/7 days, Haiku only, no tools
    - seeker: 200 messages/month, Haiku + Sonnet, tools enabled ($10/mo)
    - adept: 1000 messages/month, all models, 50 Opus msgs, BYOK ($30/mo)
    - opus: 5000 messages/month, all models, 500 Opus msgs, API access ($100/mo)
    - azothic: 20000 messages/month, all models, 2000 Opus msgs, full access ($300/mo)
    """

    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # User relationship (one subscription per user)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )

    # Stripe identifiers
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Subscription status
    tier: Mapped[str] = mapped_column(String(20), default="free_trial")  # free_trial, seeker, adept, opus, azothic
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, past_due, canceled, trialing

    # Billing period (from Stripe)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Usage tracking (reset each billing period)
    messages_used: Mapped[int] = mapped_column(Integer, default=0)
    messages_limit: Mapped[int] = mapped_column(Integer, default=50)  # Based on tier

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationship
    user = relationship("User", back_populates="subscription")

    def __repr__(self):
        return f"<Subscription {self.tier} for user {self.user_id}>"


class CreditBalance(Base):
    """
    User credit balance for pay-per-use after subscription limits.

    Credits are stored in cents (1 credit = 1 cent = $0.01)
    - $5 purchase = 500 credits
    - $20 purchase = 2500 credits (25% bonus)
    """

    __tablename__ = "credit_balances"
    __table_args__ = (
        CheckConstraint('balance_cents >= 0', name='ck_credit_balance_non_negative'),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # User relationship (one balance per user)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )

    # Balance in cents ($0.01 = 1 cent)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Lifetime totals for analytics
    total_purchased_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_used_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationship
    user = relationship("User", back_populates="credit_balance")

    def __repr__(self):
        return f"<CreditBalance ${self.balance_cents/100:.2f} for user {self.user_id}>"


class CreditTransaction(Base):
    """
    Audit log for all credit transactions.

    Transaction types:
    - purchase: User bought credits via Stripe
    - usage: Credits deducted for AI usage
    - refund: Credits refunded
    - bonus: Promotional credits added
    - subscription_bonus: Credits from subscription perks
    """

    __tablename__ = "credit_transactions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # User reference
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # Transaction details
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Positive or negative
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)  # Balance after transaction

    # Type and description
    transaction_type: Mapped[str] = mapped_column(String(50))  # purchase, usage, refund, bonus
    description: Mapped[Optional[str]] = mapped_column(String(500))

    # External references
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255))
    message_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL")
    )

    # Extra data (model used, tokens, etc.)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        index=True
    )

    def __repr__(self):
        return f"<CreditTransaction {self.transaction_type} {self.amount_cents}c for user {self.user_id}>"


class WebhookEvent(Base):
    """
    Stripe webhook event log for idempotency.

    Stores the Stripe event ID to prevent duplicate processing.
    Also keeps payload for debugging.
    """

    __tablename__ = "webhook_events"

    # Stripe event ID as primary key (ensures uniqueness)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Event details
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Processing timestamp
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    # Full payload for debugging
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    def __repr__(self):
        return f"<WebhookEvent {self.id} {self.event_type}>"


class Coupon(Base):
    """
    Promotional coupons for discounts, credits, and tier upgrades.

    Coupon types:
    - credit_bonus: Add free credits to user's balance
    - tier_upgrade: Grant temporary tier access (e.g., 1 month Adept)
    - subscription_discount: Percentage off subscription (future Stripe integration)
    """

    __tablename__ = "coupons"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # Coupon code (case-insensitive, stored uppercase)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    # Coupon details
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # Display name
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Type and value
    coupon_type: Mapped[str] = mapped_column(String(30), nullable=False)  # credit_bonus, tier_upgrade, subscription_discount
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # Credits for credit_bonus, days for tier_upgrade, % for discount
    tier: Mapped[Optional[str]] = mapped_column(String(20))  # Target tier for tier_upgrade (pro, opus)

    # Usage limits
    max_uses: Mapped[Optional[int]] = mapped_column(Integer)  # Total max uses (None = unlimited)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1)  # Per-user limit
    current_uses: Mapped[int] = mapped_column(Integer, default=0)

    # Validity period
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # None = never expires

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Admin tracking
    created_by: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    redemptions: Mapped[list["CouponRedemption"]] = relationship(back_populates="coupon", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Coupon {self.code} ({self.coupon_type})>"

    def is_valid(self) -> bool:
        """Check if coupon is currently valid."""
        if not self.is_active:
            return False
        from datetime import timezone
        now = datetime.now(timezone.utc)
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        return True


class CouponRedemption(Base):
    """
    Track which users have redeemed which coupons.

    Stores the benefit granted for audit purposes.
    """

    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        UniqueConstraint('coupon_id', 'user_id', name='uq_coupon_user_redemption'),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    # References
    coupon_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coupons.id", ondelete="CASCADE"),
        index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )

    # What was granted
    benefit_type: Mapped[str] = mapped_column(String(30))  # credit_bonus, tier_upgrade
    benefit_value: Mapped[int] = mapped_column(Integer)  # Credits added or days granted
    benefit_details: Mapped[Optional[dict]] = mapped_column(JSONB)  # Extra info (tier, expiry date, etc.)

    # Timestamp
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    coupon: Mapped["Coupon"] = relationship(back_populates="redemptions")

    def __repr__(self):
        return f"<CouponRedemption {self.coupon_id} by {self.user_id}>"
