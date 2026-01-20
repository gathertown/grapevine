import { getConfigValue } from '../../config/index.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { Octokit } from '@octokit/rest';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { ConfigKey, ConfigValue } from '../../config/types.js';
import { configString } from '../common/utils.js';

/**
 * Fetch all organizations accessible by a GitHub token
 * @param githubToken - The GitHub Personal Access Token
 * @returns Array of organization login names
 */
async function fetchUserOrganizations(githubToken: string): Promise<string[]> {
  try {
    const octokit = new Octokit({
      auth: githubToken,
    });

    logger.info('Fetching user organizations from GitHub API');

    // Get all organizations for the authenticated user
    const { data: organizations } = await octokit.rest.orgs.listForAuthenticatedUser({
      per_page: 100, // GitHub's max per page
    });

    const orgNames = organizations.map((org) => org.login);
    logger.info('GitHub organizations found', {
      count: orgNames.length,
      organizations: orgNames,
    });

    return orgNames;
  } catch (error) {
    logger.error('Error fetching GitHub organizations', error);
    // Return empty array on error to allow the process to continue
    return [];
  }
}

/**
 * Handle GitHub PAT save event by setting up webhooks and triggering initial data ingestion
 * @param tenantId - The tenant/organization ID
 * @param githubToken - The GitHub Personal Access Token
 */
async function handleGitHubTokenSaved(tenantId: string, _githubToken: string): Promise<void> {
  try {
    logger.info('GitHub PAT saved, triggering setup', { tenant_id: tenantId });

    // Get the GitHub token from config to fetch organizations
    const githubToken = await getConfigValue('GITHUB_TOKEN', tenantId);
    if (!githubToken || typeof githubToken !== 'string') {
      logger.warn('No GitHub token found, skipping organization discovery', {
        tenant_id: tenantId,
      });
      return;
    }

    // Fetch organizations accessible by this token
    const organizations = await fetchUserOrganizations(githubToken);
    if (organizations.length === 0) {
      // This is effectively a fatal error - it likely means the user didn't grant org member read access
      // We need to be able to pull the user's orgs from the GitHub API to kick off backfill
      // TODO: we should really have them select orgs and/or repos in the UI
      throw new Error(
        `No organizations found for tenant ${tenantId} - please grant org member read access`
      );
    }

    logger.info('Found organizations for GitHub token', {
      tenant_id: tenantId,
      organizationCount: organizations.length,
    });

    // Update Notion CRM - GitHub integration connected
    await updateIntegrationStatus(tenantId, 'github', true);

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering GitHub backfill ingest jobs', { tenant_id: tenantId });

      // Trigger GitHub API ingestion to pull existing data
      await Promise.all([
        sqsClient.sendGitHubPRBackfillIngestJob(tenantId, {
          organizations: [], // all orgs, for now
          repositories: [], // all repos, for now
        }),
        sqsClient.sendGitHubFileBackfillIngestJob(
          tenantId,
          [], // all repos for now
          [] // all orgs, for now
        ),
      ]);

      logger.info('GitHub backfill ingest jobs queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping GitHub API backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Error handling GitHub PAT save', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the config save if post-processing fails
  }
}

const isGithubComplete = (
  config: Record<ConfigKey, ConfigValue>,
  additionalInfo: Record<string, unknown>
) => {
  // GitHub is complete if GitHub App is installed OR legacy PAT setup is complete
  const hasGitHubApp = !!additionalInfo.ghInstalled;

  // Check legacy PAT setup as fallback
  const githubToken = configString(config.GITHUB_TOKEN);
  const tokenValid =
    (githubToken.trim().startsWith('ghp_') || githubToken.trim().startsWith('github_pat_')) &&
    githubToken.trim().length > 10;
  const setupMarkedComplete = configString(config.GITHUB_SETUP_COMPLETE) === 'true';
  const hasLegacySetup = tokenValid && setupMarkedComplete;

  return hasGitHubApp || hasLegacySetup;
};

export { handleGitHubTokenSaved, isGithubComplete };
