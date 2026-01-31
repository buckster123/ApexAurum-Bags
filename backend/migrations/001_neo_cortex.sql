-- Neo-Cortex Migration: Add unified memory columns to user_vectors
-- Run this on Railway PostgreSQL: psql $DATABASE_URL -f migrations/001_neo_cortex.sql
--
-- This adds the columns needed for Neo-Cortex unified memory system:
-- - Memory layers (sensory/working/long_term/cortex)
-- - Visibility realms (private/village/bridge)
-- - Agent identity
-- - Attention tracking

-- Add columns if they don't exist (safe to re-run)

-- Memory layer (sensory -> working -> long_term -> cortex)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'layer') THEN
        ALTER TABLE user_vectors ADD COLUMN layer VARCHAR(20) DEFAULT 'working' NOT NULL;
    END IF;
END $$;

-- Visibility realm (private/village/bridge)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'visibility') THEN
        ALTER TABLE user_vectors ADD COLUMN visibility VARCHAR(20) DEFAULT 'private' NOT NULL;
    END IF;
END $$;

-- Agent identity (AZOTH, ELYSIAN, CLAUDE, etc.)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'agent_id') THEN
        ALTER TABLE user_vectors ADD COLUMN agent_id VARCHAR(50);
    END IF;
END $$;

-- Message type (observation/dialogue/fact/question/etc.)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'message_type') THEN
        ALTER TABLE user_vectors ADD COLUMN message_type VARCHAR(50) DEFAULT 'observation' NOT NULL;
    END IF;
END $$;

-- Attention weight (0.0 - 2.0, boosted by access)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'attention_weight') THEN
        ALTER TABLE user_vectors ADD COLUMN attention_weight FLOAT DEFAULT 1.0 NOT NULL;
    END IF;
END $$;

-- Access count (how many times retrieved)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'access_count') THEN
        ALTER TABLE user_vectors ADD COLUMN access_count INTEGER DEFAULT 0 NOT NULL;
    END IF;
END $$;

-- Last accessed timestamp
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'last_accessed_at') THEN
        ALTER TABLE user_vectors ADD COLUMN last_accessed_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Responding to (IDs of memories this responds to)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'responding_to') THEN
        ALTER TABLE user_vectors ADD COLUMN responding_to JSONB DEFAULT '[]'::jsonb NOT NULL;
    END IF;
END $$;

-- Conversation thread ID
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'conversation_thread') THEN
        ALTER TABLE user_vectors ADD COLUMN conversation_thread VARCHAR(100);
    END IF;
END $$;

-- Related agents (for bridge visibility)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'related_agents') THEN
        ALTER TABLE user_vectors ADD COLUMN related_agents JSONB DEFAULT '[]'::jsonb NOT NULL;
    END IF;
END $$;

-- Tags for organization
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'user_vectors' AND column_name = 'tags') THEN
        ALTER TABLE user_vectors ADD COLUMN tags JSONB DEFAULT '[]'::jsonb NOT NULL;
    END IF;
END $$;

-- Create indexes for common queries (if they don't exist)
CREATE INDEX IF NOT EXISTS idx_vectors_layer ON user_vectors(layer);
CREATE INDEX IF NOT EXISTS idx_vectors_visibility ON user_vectors(visibility);
CREATE INDEX IF NOT EXISTS idx_vectors_agent ON user_vectors(agent_id);
CREATE INDEX IF NOT EXISTS idx_vectors_user_visibility ON user_vectors(user_id, visibility);
CREATE INDEX IF NOT EXISTS idx_vectors_user_layer ON user_vectors(user_id, layer);

-- Output success
SELECT 'Neo-Cortex migration complete!' as status,
       count(*) as total_vectors
FROM user_vectors;
