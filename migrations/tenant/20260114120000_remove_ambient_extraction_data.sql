-- Migration: remove_ambient_extraction_data
-- Created: 2026-01-14 12:00:00

-- Remove ambient extraction data now that the feature is retired.
DELETE FROM ambient_extraction_channels;
DELETE FROM ambient_document_state;
DELETE FROM ambient_source_config;
DELETE FROM slack_ambient_thread_state;
