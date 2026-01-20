-- Add optimized indexes for citation resolver queries
-- These indexes target specific queries in the citation resolution system

-- Slack citation resolver optimization
-- Optimizes query: SELECT * FROM ingest_artifact WHERE entity='slack_message' 
--                   AND metadata->>'channel_id'=$1 AND date_range_filter
CREATE INDEX IF NOT EXISTS idx_ingest_artifact_slack_channel_date
ON ingest_artifact (
    (metadata->>'channel_id'),
    source_updated_at
)
WHERE entity = 'slack_message'
  AND metadata ? 'channel_id';

-- Notion citation resolver optimization  
-- Optimizes query: SELECT metadata->'block_ids', content FROM chunks
--                   WHERE document_id=$1 AND metadata ? 'block_ids' ORDER BY created_at
CREATE INDEX IF NOT EXISTS idx_chunks_notion_blocks
ON chunks (document_id, created_at ASC)
WHERE metadata ? 'block_ids';