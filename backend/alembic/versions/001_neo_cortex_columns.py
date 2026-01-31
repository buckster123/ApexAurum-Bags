"""
Add Neo-Cortex columns to user_vectors

This migration adds the columns needed for Neo-Cortex unified memory system:
- Memory layers (sensory/working/long_term/cortex)
- Visibility realms (private/village/bridge)
- Agent identity
- Attention tracking (access_count, last_accessed_at, attention_weight)
- Village Protocol fields (responding_to, conversation_thread, related_agents)
- Message type and tags

Revision ID: 001_neo_cortex
Revises:
Create Date: 2026-01-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '001_neo_cortex'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Neo-Cortex columns to user_vectors table."""

    # Memory layer (sensory -> working -> long_term -> cortex)
    op.add_column('user_vectors',
        sa.Column('layer', sa.String(20), nullable=False, server_default='working')
    )

    # Visibility realm (private/village/bridge)
    op.add_column('user_vectors',
        sa.Column('visibility', sa.String(20), nullable=False, server_default='private')
    )

    # Agent identity (AZOTH, ELYSIAN, CLAUDE, etc.)
    op.add_column('user_vectors',
        sa.Column('agent_id', sa.String(50), nullable=True)
    )

    # Message type (observation/dialogue/fact/question/etc.)
    op.add_column('user_vectors',
        sa.Column('message_type', sa.String(50), nullable=False, server_default='observation')
    )

    # Attention/health tracking
    op.add_column('user_vectors',
        sa.Column('attention_weight', sa.Float, nullable=False, server_default='1.0')
    )
    op.add_column('user_vectors',
        sa.Column('access_count', sa.Integer, nullable=False, server_default='0')
    )
    op.add_column('user_vectors',
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Village Protocol fields (stored as JSONB for flexibility)
    op.add_column('user_vectors',
        sa.Column('responding_to', JSONB, nullable=False, server_default='[]')
    )
    op.add_column('user_vectors',
        sa.Column('conversation_thread', sa.String(100), nullable=True)
    )
    op.add_column('user_vectors',
        sa.Column('related_agents', JSONB, nullable=False, server_default='[]')
    )
    op.add_column('user_vectors',
        sa.Column('tags', JSONB, nullable=False, server_default='[]')
    )

    # Add indexes for common queries
    op.create_index('idx_vectors_layer', 'user_vectors', ['layer'])
    op.create_index('idx_vectors_visibility', 'user_vectors', ['visibility'])
    op.create_index('idx_vectors_agent', 'user_vectors', ['agent_id'])
    op.create_index('idx_vectors_user_visibility', 'user_vectors', ['user_id', 'visibility'])
    op.create_index('idx_vectors_user_layer', 'user_vectors', ['user_id', 'layer'])


def downgrade() -> None:
    """Remove Neo-Cortex columns from user_vectors table."""

    # Drop indexes first
    op.drop_index('idx_vectors_user_layer')
    op.drop_index('idx_vectors_user_visibility')
    op.drop_index('idx_vectors_agent')
    op.drop_index('idx_vectors_visibility')
    op.drop_index('idx_vectors_layer')

    # Drop columns
    op.drop_column('user_vectors', 'tags')
    op.drop_column('user_vectors', 'related_agents')
    op.drop_column('user_vectors', 'conversation_thread')
    op.drop_column('user_vectors', 'responding_to')
    op.drop_column('user_vectors', 'last_accessed_at')
    op.drop_column('user_vectors', 'access_count')
    op.drop_column('user_vectors', 'attention_weight')
    op.drop_column('user_vectors', 'message_type')
    op.drop_column('user_vectors', 'agent_id')
    op.drop_column('user_vectors', 'visibility')
    op.drop_column('user_vectors', 'layer')
