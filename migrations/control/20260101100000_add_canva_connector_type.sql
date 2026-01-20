-- Control DB Migration: add_canva_connector_type
-- Created: 2026-01-01 10:00:00
-- Description: Add 'canva' to the valid_connector_type constraint for design platform integration

BEGIN;

ALTER TABLE connector_installations
DROP CONSTRAINT valid_connector_type;

ALTER TABLE connector_installations
ADD CONSTRAINT valid_connector_type CHECK (type IN (
    'slack', 'github', 'linear', 'notion', 'google_drive', 'google_email',
    'hubspot', 'salesforce', 'jira', 'confluence', 'gong', 'gather',
    'trello', 'zendesk', 'asana', 'intercom', 'snowflake', 'attio', 'fireflies',
    'clickup', 'gitlab', 'pylon', 'monday', 'pipedrive', 'figma', 'posthog', 'canva'
));

COMMIT;
