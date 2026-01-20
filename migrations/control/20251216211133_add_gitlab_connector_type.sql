-- Control DB Migration: add_gitlab_connector_type
-- Created: 2025-12-16 21:11:33

BEGIN;

ALTER TABLE connector_installations
DROP CONSTRAINT valid_connector_type;

ALTER TABLE connector_installations
ADD CONSTRAINT valid_connector_type CHECK (type IN (
    'slack', 'github', 'linear', 'notion', 'google_drive', 'google_email',
    'hubspot', 'salesforce', 'jira', 'confluence', 'gong', 'gather',
    'trello', 'zendesk', 'asana', 'intercom', 'snowflake', 'attio', 'fireflies',
    'clickup', 'gitlab'
));

COMMIT;
