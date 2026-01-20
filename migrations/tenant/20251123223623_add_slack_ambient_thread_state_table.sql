-- Add slack_ambient_thread_state table for tracking ambient extraction state with locking
-- Ported from Exponent's SlackThreadState table
-- Schema matches Exponent's packages/task-infra/prisma/schema.prisma

CREATE TABLE IF NOT EXISTS slack_ambient_thread_state (
    id VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    
    -- Thread identification (matches Exponent's unique constraint)
    team_id VARCHAR(255) NOT NULL DEFAULT '__default__',
    channel_id VARCHAR(255) NOT NULL,
    thread_ts VARCHAR(255) NOT NULL,
    
    -- Processing status and locking
    status VARCHAR(50) NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'queued', 'processing', 'failed')),
    queue_token VARCHAR(255),
    latest_enqueued_event_ts VARCHAR(255),
    
    -- Deduplication tracking
    last_processed_message_ts VARCHAR(255),
    last_processed_message_hash VARCHAR(255),
    
    -- Re-queueing coordination
    needs_reprocess BOOLEAN DEFAULT false,
    
    -- Lock management
    processing_job_id VARCHAR(255),
    locked_at TIMESTAMP WITH TIME ZONE,
    lock_expires_at TIMESTAMP WITH TIME ZONE,
    
    -- Error handling
    failure_reason TEXT,
    attempts INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure uniqueness per thread (matches Exponent's @@unique)
    UNIQUE (channel_id, thread_ts, team_id)
);

-- Index for status-based queries
CREATE INDEX IF NOT EXISTS idx_slack_ambient_thread_state_status 
    ON slack_ambient_thread_state(status);

-- Index for queue token lookups
CREATE INDEX IF NOT EXISTS idx_slack_ambient_thread_state_queue_token 
    ON slack_ambient_thread_state(queue_token) 
    WHERE queue_token IS NOT NULL;

-- Index for finding expired locks
CREATE INDEX IF NOT EXISTS idx_slack_ambient_thread_state_lock_expires 
    ON slack_ambient_thread_state(lock_expires_at) 
    WHERE lock_expires_at IS NOT NULL;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_slack_ambient_thread_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_slack_ambient_thread_state_updated_at
    BEFORE UPDATE ON slack_ambient_thread_state
    FOR EACH ROW
    EXECUTE FUNCTION update_slack_ambient_thread_state_updated_at();
