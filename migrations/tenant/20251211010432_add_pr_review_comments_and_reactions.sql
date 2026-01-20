-- Tenant DB Migration: add pr review comments and reactions
-- Created: 2025-12-11 01:04:32

BEGIN;

-- Create pr_review_comments table
-- Stores metadata about each PR review comment posted by Grapevine
CREATE TABLE pr_review_comments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    github_comment_id BIGINT UNIQUE NOT NULL,
    github_review_id BIGINT NOT NULL,
    github_pr_number INTEGER NOT NULL,
    github_repo_owner VARCHAR(255) NOT NULL,
    github_repo_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    position INTEGER,
    impact INTEGER,
    confidence INTEGER,
    categories JSONB,
    github_comment_url TEXT,
    github_review_url TEXT,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexes for pr_review_comments
CREATE INDEX pr_review_comments_review_id_idx ON pr_review_comments(github_review_id);
CREATE INDEX pr_review_comments_pr_idx ON pr_review_comments(github_repo_owner, github_repo_name, github_pr_number);
CREATE INDEX pr_review_comments_impact_idx ON pr_review_comments(impact DESC) WHERE impact IS NOT NULL;
CREATE INDEX pr_review_comments_created_at_idx ON pr_review_comments(created_at DESC);

-- Constraints for pr_review_comments
ALTER TABLE pr_review_comments ADD CONSTRAINT pr_review_comments_impact_range
    CHECK (impact IS NULL OR (impact >= 0 AND impact <= 100));

ALTER TABLE pr_review_comments ADD CONSTRAINT pr_review_comments_confidence_range
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 100));

-- Trigger for auto-updating updated_at
CREATE TRIGGER update_pr_review_comments_updated_at
    BEFORE UPDATE ON pr_review_comments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create pr_review_comment_reactions table
-- Stores user reactions (thumbs up/down) synced from GitHub
CREATE TABLE pr_review_comment_reactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    comment_id UUID NOT NULL REFERENCES pr_review_comments(id) ON DELETE CASCADE,
    github_username VARCHAR(255) NOT NULL,
    reaction_type VARCHAR(20) NOT NULL,
    synced_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(comment_id, github_username, reaction_type)
);

-- Indexes for pr_review_comment_reactions
CREATE INDEX pr_review_comment_reactions_comment_id_idx ON pr_review_comment_reactions(comment_id);
CREATE INDEX pr_review_comment_reactions_username_idx ON pr_review_comment_reactions(github_username);
CREATE INDEX pr_review_comment_reactions_type_idx ON pr_review_comment_reactions(reaction_type);
CREATE INDEX pr_review_comment_reactions_synced_at_idx ON pr_review_comment_reactions(synced_at DESC);

-- Constraints for pr_review_comment_reactions
ALTER TABLE pr_review_comment_reactions ADD CONSTRAINT pr_review_comment_reactions_type_check
    CHECK (reaction_type IN ('thumbs_up', 'thumbs_down'));

-- Trigger for auto-updating updated_at
CREATE TRIGGER update_pr_review_comment_reactions_updated_at
    BEFORE UPDATE ON pr_review_comment_reactions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
