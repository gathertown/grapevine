-- Add sample_questions table for first-time questions feature
-- This table stores curated questions extracted from Slack data to help new users understand what the system can answer

CREATE TABLE sample_questions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question_text TEXT NOT NULL,
    channel_name VARCHAR(255),
    channel_id VARCHAR(255),
    user_id VARCHAR(255),
    username VARCHAR(255),
    message_timestamp TIMESTAMP WITH TIME ZONE,
    source_message_id VARCHAR(255),
    thread_reply_count INTEGER DEFAULT 0,
    reaction_count INTEGER DEFAULT 0,
    score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX idx_sample_questions_score ON sample_questions(score DESC);
CREATE UNIQUE INDEX idx_sample_questions_unique_message ON sample_questions(source_message_id);