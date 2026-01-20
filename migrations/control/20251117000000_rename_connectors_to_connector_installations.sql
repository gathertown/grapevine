-- Migration: Rename connectors table to connector_installations
-- Date: 2025-11-17

-- Rename the table
ALTER TABLE connectors RENAME TO connector_installations;

-- Rename foreign key constraint (only if it uses the old table name)
ALTER TABLE connector_installations RENAME CONSTRAINT connectors_tenant_id_fkey TO connector_installations_tenant_id_fkey;

-- Rename indexes that reference the old table name
ALTER INDEX idx_connectors_tenant_id RENAME TO idx_connector_installations_tenant_id;
ALTER INDEX idx_connectors_status RENAME TO idx_connector_installations_status;

-- Rename trigger that references the old table name
ALTER TRIGGER update_connectors_updated_at ON connector_installations RENAME TO update_connector_installations_updated_at;
