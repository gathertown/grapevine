-- Create table to track Trello GDPR compliance polling
-- This table tracks when we last polled Trello's compliance API
-- and which compliance records we've processed

CREATE TABLE IF NOT EXISTS trello_compliance_tracking (
    id SERIAL PRIMARY KEY,
    last_poll_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_processed_record_date TIMESTAMP WITH TIME ZONE,
    records_processed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create table to store processed compliance records
-- This helps us avoid reprocessing the same records
CREATE TABLE IF NOT EXISTS trello_compliance_records (
    id SERIAL PRIMARY KEY,
    member_id VARCHAR(255) NOT NULL,
    record_type VARCHAR(50) NOT NULL, -- 'memberDelete' or 'memberProfileUpdate'
    record_date TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(member_id, record_type, record_date)
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_trello_compliance_records_member_id 
    ON trello_compliance_records(member_id);
CREATE INDEX IF NOT EXISTS idx_trello_compliance_records_record_date 
    ON trello_compliance_records(record_date);
CREATE INDEX IF NOT EXISTS idx_trello_compliance_records_processed_at 
    ON trello_compliance_records(processed_at);

