-- Control DB Migration: add_pipedrive_connector_type
-- Created: 2025-12-24 10:05:41
-- Description: Add 'pipedrive' to the valid_connector_type constraint for CRM integration

BEGIN;

ALTER TABLE connector_installations
DROP CONSTRAINT valid_connector_type;

ALTER TABLE connector_installations
ADD CONSTRAINT valid_connector_type CHECK (type IN (
    'slack', 'github', 'linear', 'notion', 'google_drive', 'google_email',
    'hubspot', 'salesforce', 'jira', 'confluence', 'gong', 'gather',
    'trello', 'zendesk', 'asana', 'intercom', 'snowflake', 'attio', 'fireflies',
    'clickup', 'gitlab', 'pylon', 'monday', 'pipedrive'
));

COMMIT;
