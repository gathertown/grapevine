-- Create document_permissions table to store permission policies
-- Note: We don't add foreign key constraint here to avoid dependency on documents table order
CREATE TABLE IF NOT EXISTS document_permissions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id VARCHAR(255) UNIQUE NOT NULL,
    permission_policy VARCHAR(10) NOT NULL DEFAULT 'private' CHECK (permission_policy IN ('tenant', 'private')),
    permission_allowed_tokens TEXT[] DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_document_permissions_document_id ON document_permissions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_permissions_policy ON document_permissions(permission_policy);

-- Add foreign key constraint only if documents table exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'documents') THEN
        -- Add foreign key constraint if it doesn't already exist
        IF NOT EXISTS (
            SELECT FROM information_schema.table_constraints 
            WHERE constraint_name = 'document_permissions_document_id_fkey'
            AND table_name = 'document_permissions'
        ) THEN
            ALTER TABLE document_permissions 
            ADD CONSTRAINT document_permissions_document_id_fkey 
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

-- Add permissions column to ingest_artifact table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ingest_artifact') THEN
        IF NOT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'ingest_artifact' AND column_name = 'permissions'
        ) THEN
            ALTER TABLE ingest_artifact ADD COLUMN permissions JSONB;
        END IF;
    END IF;
END $$;

-- Backfill existing documents with tenant policy (all current data is tenant accessible)
-- Only run if documents table exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'documents') THEN
        INSERT INTO document_permissions (document_id, permission_policy, permission_allowed_tokens)
        SELECT 
            id as document_id,
            'tenant' as permission_policy,
            NULL as permission_allowed_tokens
        FROM documents
        ON CONFLICT (document_id) DO NOTHING;
    END IF;
END $$;

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_document_permissions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger only if it doesn't already exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.triggers 
        WHERE trigger_name = 'document_permissions_updated_at_trigger'
        AND event_object_table = 'document_permissions'
    ) THEN
        CREATE TRIGGER document_permissions_updated_at_trigger
        BEFORE UPDATE ON document_permissions
        FOR EACH ROW
        EXECUTE FUNCTION update_document_permissions_updated_at();
    END IF;
END $$;