-- Add ambient extraction channel configuration table
-- Maps Slack channels to Linear teams for ambient extraction

CREATE TABLE IF NOT EXISTS ambient_extraction_channels (
    id VARCHAR(255) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    
    -- Channel identification
    channel_id VARCHAR(255) NOT NULL,
    channel_name VARCHAR(255),
    
    -- Linear team mapping
    linear_team_id VARCHAR(255) NOT NULL,
    linear_team_name VARCHAR(255),
    
    -- Configuration
    enabled BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure uniqueness per channel
    UNIQUE (channel_id)
);

-- Index for enabled lookups
CREATE INDEX IF NOT EXISTS idx_ambient_channels_enabled 
    ON ambient_extraction_channels(enabled) 
    WHERE enabled = true;

-- Index for Linear team lookups
CREATE INDEX IF NOT EXISTS idx_ambient_channels_linear_team 
    ON ambient_extraction_channels(linear_team_id);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_ambient_extraction_channels_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ambient_extraction_channels_updated_at
    BEFORE UPDATE ON ambient_extraction_channels
    FOR EACH ROW
    EXECUTE FUNCTION update_ambient_extraction_channels_updated_at();
