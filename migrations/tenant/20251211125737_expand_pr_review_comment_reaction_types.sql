-- Tenant DB Migration: expand pr review comment reaction types
-- Created: 2025-12-11 12:57:37

BEGIN;

-- Drop the old constraint that only allowed thumbs_up and thumbs_down
ALTER TABLE pr_review_comment_reactions
    DROP CONSTRAINT pr_review_comment_reactions_type_check;

-- Add new constraint with all GitHub reaction types
-- GitHub supports: +1, -1, laugh, confused, heart, hooray, rocket, eyes
-- Stored as: thumbs_up, thumbs_down, laugh, confused, heart, hooray, rocket, eyes
ALTER TABLE pr_review_comment_reactions
    ADD CONSTRAINT pr_review_comment_reactions_type_check
    CHECK (reaction_type IN (
        'thumbs_up', 'thumbs_down', 'laugh', 'confused',
        'heart', 'hooray', 'rocket', 'eyes'
    ));

COMMIT;
