"""
Add billing tables for subscriptions and credits

Creates the billing infrastructure for ApexAurum monetization:
- subscriptions: Stripe subscription sync (tier, status, usage)
- credit_balances: Pay-per-use credit balances
- credit_transactions: Audit log for all credit changes
- webhook_events: Stripe webhook idempotency

Revision ID: 002_billing_tables
Revises: 001_neo_cortex
Create Date: 2026-01-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '002_billing_tables'
down_revision = '001_neo_cortex'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create billing tables."""

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBSCRIPTIONS TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        'subscriptions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True, nullable=False),

        # Stripe identifiers
        sa.Column('stripe_customer_id', sa.String(255), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(255), unique=True, nullable=True),
        sa.Column('stripe_price_id', sa.String(255), nullable=True),

        # Subscription status
        sa.Column('tier', sa.String(20), nullable=False, server_default='free'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),

        # Billing period
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean, nullable=False, server_default='false'),

        # Usage tracking
        sa.Column('messages_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_limit', sa.Integer, nullable=False, server_default='50'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # CREDIT BALANCES TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        'credit_balances',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True, nullable=False),

        # Balance in cents
        sa.Column('balance_cents', sa.Integer, nullable=False, server_default='0'),

        # Lifetime totals
        sa.Column('total_purchased_cents', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_used_cents', sa.Integer, nullable=False, server_default='0'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # CREDIT TRANSACTIONS TABLE (Audit Log)
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        'credit_transactions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Transaction details
        sa.Column('amount_cents', sa.Integer, nullable=False),
        sa.Column('balance_after', sa.Integer, nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),

        # External references
        sa.Column('stripe_payment_intent_id', sa.String(255), nullable=True),
        sa.Column('message_id', UUID(as_uuid=True), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),

        # Extra data (model, tokens, etc.)
        sa.Column('extra_data', JSONB, nullable=True),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Indexes for common queries
    op.create_index('idx_credit_tx_user', 'credit_transactions', ['user_id'])
    op.create_index('idx_credit_tx_created', 'credit_transactions', ['created_at'])
    op.create_index('idx_credit_tx_type', 'credit_transactions', ['transaction_type'])

    # ═══════════════════════════════════════════════════════════════════════════
    # WEBHOOK EVENTS TABLE (Idempotency)
    # ═══════════════════════════════════════════════════════════════════════════
    op.create_table(
        'webhook_events',
        # Stripe event ID as primary key
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('payload', JSONB, nullable=True),
    )


def downgrade() -> None:
    """Drop billing tables."""

    op.drop_table('webhook_events')

    op.drop_index('idx_credit_tx_type')
    op.drop_index('idx_credit_tx_created')
    op.drop_index('idx_credit_tx_user')
    op.drop_table('credit_transactions')

    op.drop_table('credit_balances')
    op.drop_table('subscriptions')
