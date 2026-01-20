-- Control DB Migration: drop legacy *_installations tables
-- Created: 2025-12-03
--
-- These tables have been superseded by the unified connector_installations table.
-- All data has been migrated to connector_installations.

BEGIN;

-- Drop triggers first
DROP TRIGGER IF EXISTS update_slack_installations_updated_at ON public.slack_installations;
DROP TRIGGER IF EXISTS update_github_installations_updated_at ON public.github_installations;
DROP TRIGGER IF EXISTS update_linear_installations_updated_at ON public.linear_installations;
DROP TRIGGER IF EXISTS update_trello_installations_updated_at ON public.trello_installations;

-- Drop tables (CASCADE will drop indexes and constraints)
DROP TABLE IF EXISTS public.slack_installations CASCADE;
DROP TABLE IF EXISTS public.github_installations CASCADE;
DROP TABLE IF EXISTS public.linear_installations CASCADE;
DROP TABLE IF EXISTS public.trello_installations CASCADE;
DROP TABLE IF EXISTS public.hubspot_installations CASCADE;

COMMIT;
