-- Create warehouse_query_log table for logging queries to data warehouses
-- This is a generic table that logs queries across all data warehouse integrations
-- (Snowflake, BigQuery, Redshift, etc.)

CREATE TABLE warehouse_query_log (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255),                           -- NULL for system/tenant-wide queries
    source VARCHAR(50) NOT NULL,                    -- "snowflake", "bigquery", "redshift", etc.
    query_type VARCHAR(50) NOT NULL,                -- "natural_language" or "sql"
    question TEXT NOT NULL,                         -- Original question or SQL statement
    generated_sql TEXT,                             -- NULL if query_type="sql"
    semantic_model_id VARCHAR(255),                 -- NULL if not applicable
    execution_time_ms INTEGER,
    row_count INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common query patterns
CREATE INDEX idx_warehouse_query_log_user_source ON warehouse_query_log(user_id, source);
CREATE INDEX idx_warehouse_query_log_created_at ON warehouse_query_log(created_at DESC);
CREATE INDEX idx_warehouse_query_log_source_success ON warehouse_query_log(source, success);
