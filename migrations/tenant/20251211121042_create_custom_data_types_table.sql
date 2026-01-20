-- Migration: create_custom_data_types_table
-- Created at: 2025-12-11 12:10:42

CREATE TYPE custom_data_type_state AS ENUM ('enabled', 'disabled', 'deleted');

CREATE TABLE IF NOT EXISTS custom_data_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    custom_fields JSONB NOT NULL DEFAULT '{"fields": [], "version": 1}'::jsonb,
    state custom_data_type_state NOT NULL DEFAULT 'enabled',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_custom_data_types_slug ON custom_data_types(slug);
CREATE INDEX IF NOT EXISTS idx_custom_data_types_state ON custom_data_types(state);

CREATE TRIGGER update_custom_data_types_updated_at
    BEFORE UPDATE ON custom_data_types
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
