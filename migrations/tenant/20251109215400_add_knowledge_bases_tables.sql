-- Create knowledge_bases table
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create knowledge_base_articles table
CREATE TABLE knowledge_base_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(kb_id, title)
);

-- Create indexes for better query performance
CREATE INDEX idx_kb_articles_kb_id ON knowledge_base_articles(kb_id);
CREATE INDEX idx_kb_articles_title ON knowledge_base_articles(title);

-- Add comment on config column
COMMENT ON COLUMN knowledge_bases.config IS 'JSONB containing: context_gathering_prompt (string), template (array of {field_name, field_prompt})';
COMMENT ON COLUMN knowledge_base_articles.content IS 'JSONB containing field values from template generation';
