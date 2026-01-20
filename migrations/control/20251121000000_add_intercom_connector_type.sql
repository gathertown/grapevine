-- Add intercom to valid connector types
-- Date: 2025-11-21

-- Drop the existing constraint
ALTER TABLE connector_installations DROP CONSTRAINT valid_connector_type;

-- Add the constraint with intercom included
ALTER TABLE connector_installations ADD CONSTRAINT valid_connector_type CHECK (type IN (
    'slack', 'github', 'linear', 'notion', 'google_drive', 'google_email',
    'hubspot', 'salesforce', 'jira', 'confluence', 'gong', 'gather',
    'trello', 'zendesk', 'asana', 'intercom'
));
