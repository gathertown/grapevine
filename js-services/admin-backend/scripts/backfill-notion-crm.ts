#!/usr/bin/env node
/**
 * Backfill Notion CRM Database
 *
 * This script reads all tenants from the control database, fetches their
 * organization details from WorkOS, and creates/updates records in the
 * Notion CRM database.
 *
 * Usage:
 *   npx tsx scripts/backfill-notion-crm.ts [--dry-run] [--tenant-id <tenant_id>] [--start-date <date>] [--skip-free-email-domains]
 *
 * Options:
 *   --dry-run                    Show what would be created without actually creating records
 *   --tenant-id <id>             Process only a specific tenant by ID
 *   --start-date <date>          Process only tenants created on or after this date (ISO 8601 format: YYYY-MM-DD)
 *   --skip-free-email-domains    Skip organizations that only have free email domains (gmail, hotmail, etc.)
 */

import {
  getControlDbPool,
  closeControlDbPool,
  getGitHubInstallationId,
} from '../src/control-db.js';
import { getWorkOSClient } from '../src/workos-client.js';
import {
  createCustomerRecord,
  updateCustomerRecord,
  findPageIdForTenant,
  updateSlackBotStatus,
  updateIntegrationStatus,
  ensureNotionProperties,
  type CustomerRecordData,
} from '../src/utils/notion-crm.js';
import { getAllConfigValues } from '../src/config/index.js';
import { logger } from '../src/utils/logger.js';

interface TenantRow {
  id: string;
  workos_org_id: string;
  state: string;
  billing_mode: string;
  created_at: Date;
  provisioned_at: Date | null;
}

interface WorkOSOrganization {
  id: string;
  name: string;
}

interface BackfillStats {
  totalTenants: number;
  provisioned: number;
  notProvisioned: number;
  created: number;
  updated: number;
  failed: number;
  skipped: number;
}

interface IntegrationStatus {
  slack: boolean;
  github: boolean;
  notion: boolean;
  linear: boolean;
  googleDrive: boolean;
  googleEmail: boolean;
  salesforce: boolean;
  hubspot: boolean;
  jira: boolean;
  confluence: boolean;
}

async function getAllTenants(tenantId?: string, startDate?: Date): Promise<TenantRow[]> {
  const pool = getControlDbPool();
  if (!pool) {
    throw new Error('Control database not available');
  }

  // If specific tenant ID provided, query for just that tenant
  if (tenantId) {
    const result = await pool.query<TenantRow>(
      `SELECT id, workos_org_id, state, billing_mode, created_at, provisioned_at
       FROM public.tenants
       WHERE id = $1`,
      [tenantId]
    );
    return result.rows;
  }

  // Otherwise, get all tenants (optionally filtered by start date)
  let query = `SELECT id, workos_org_id, state, billing_mode, created_at, provisioned_at
     FROM public.tenants`;
  const params: any[] = [];

  if (startDate) {
    query += ` WHERE created_at >= $1`;
    params.push(startDate);
  }

  query += ` ORDER BY created_at DESC`;

  const result = await pool.query<TenantRow>(query, params);

  return result.rows;
}

/**
 * Check if email domain is a common free email provider
 */
function isFreeEmailDomain(email: string): boolean {
  const domain = email.split('@')[1]?.toLowerCase();
  if (!domain) return false;

  const freeEmailDomains = [
    'gmail.com',
    'googlemail.com',
    'hotmail.com',
    'hotmail.co.uk',
    'hotmail.fr',
    'outlook.com',
    'outlook.co.uk',
    'yahoo.com',
    'yahoo.co.uk',
    'yahoo.fr',
    'aol.com',
    'icloud.com',
    'me.com',
    'mac.com',
    'protonmail.com',
    'proton.me',
    'mail.com',
    'gmx.com',
    'gmx.us',
    'zoho.com',
    'yandex.com',
    'yandex.ru',
    'testbridge.io', // Test organization
  ];

  return freeEmailDomains.includes(domain);
}

/**
 * Check if all admin emails are from free email domains
 */
function hasOnlyFreeEmailDomains(emails: string[]): boolean {
  if (emails.length === 0) return false;
  return emails.every((email) => isFreeEmailDomain(email));
}

async function getOrganizationDetails(workosOrgId: string): Promise<WorkOSOrganization | null> {
  const workos = getWorkOSClient();
  if (!workos) {
    throw new Error('WorkOS client not available');
  }

  try {
    const organization = await workos.organizations.getOrganization(workosOrgId);
    return {
      id: organization.id,
      name: organization.name,
    };
  } catch (error) {
    logger.error(`Failed to fetch organization ${workosOrgId} from WorkOS`, { error });
    return null;
  }
}

/**
 * Check which integrations are configured for a tenant by examining their config values
 */
async function checkIntegrationStatus(tenantId: string): Promise<IntegrationStatus> {
  try {
    const config = await getAllConfigValues(tenantId);

    // Helper to check if a key exists and has a truthy value
    const hasValue = (key: string) => {
      const value = config[key as keyof typeof config];
      return value !== null && value !== undefined && value !== '';
    };

    // Check for GitHub App installation in addition to config
    const hasGitHubApp = (await getGitHubInstallationId(tenantId)) !== null;

    return {
      // Slack is configured if we have bot token
      slack: hasValue('SLACK_BOT_TOKEN'),

      // GitHub is configured if we have token/setup complete OR if GitHub App is installed
      github:
        (hasValue('GITHUB_TOKEN') && config['GITHUB_SETUP_COMPLETE'] === 'true') || hasGitHubApp,

      // Notion is configured if we have token and setup is complete
      notion: hasValue('NOTION_TOKEN') && config['NOTION_COMPLETE'] === 'true',

      // Linear is configured if we have API key
      linear: hasValue('LINEAR_API_KEY'),

      // Google Drive is configured if we have admin email and service account
      googleDrive: hasValue('GOOGLE_DRIVE_ADMIN_EMAIL') && hasValue('GOOGLE_DRIVE_SERVICE_ACCOUNT'),

      // Google Email is configured if we have admin email and service account
      googleEmail: hasValue('GOOGLE_EMAIL_ADMIN_EMAIL') && hasValue('GOOGLE_EMAIL_SERVICE_ACCOUNT'),

      // Salesforce is configured if we have refresh token and instance URL
      salesforce: hasValue('SALESFORCE_REFRESH_TOKEN') && hasValue('SALESFORCE_INSTANCE_URL'),

      // HubSpot is configured if setup is complete
      hubspot: config['HUBSPOT_COMPLETE'] === 'true',

      // Jira is configured if we have cloud ID and webtrigger URL
      jira: hasValue('JIRA_CLOUD_ID') && hasValue('JIRA_WEBTRIGGER_BACKFILL_URL'),

      // Confluence is configured if we have cloud ID and webtrigger URL
      confluence: false, // Confluence config keys not fully defined yet
    };
  } catch (error) {
    logger.error(`Failed to check integration status for tenant ${tenantId}`, { error });
    // Return all false on error
    return {
      slack: false,
      github: false,
      notion: false,
      linear: false,
      googleDrive: false,
      googleEmail: false,
      salesforce: false,
      hubspot: false,
      jira: false,
      confluence: false,
    };
  }
}

async function getOrganizationAdminEmails(workosOrgId: string): Promise<string[]> {
  const workos = getWorkOSClient();
  if (!workos) {
    throw new Error('WorkOS client not available');
  }

  try {
    // List all organization memberships
    logger.info(`Fetching organization memberships for ${workosOrgId}`);
    const memberships = await workos.userManagement.listOrganizationMemberships({
      organizationId: workosOrgId,
    });

    logger.info(
      `Found ${memberships.data.length} total memberships for organization ${workosOrgId}`
    );

    // Get all active user emails (not just admins, since WorkOS may use different role names)
    const userEmails: string[] = [];
    const allRoles = new Set<string>();

    for (const membership of memberships.data) {
      const roleSlug = membership.role?.slug;
      if (roleSlug) {
        allRoles.add(roleSlug);
      }

      // Only process active memberships
      if (membership.status !== 'active') {
        logger.info(`Skipping non-active membership`, {
          userId: membership.userId,
          role: roleSlug,
          status: membership.status,
        });
        continue;
      }

      logger.info(`Processing membership`, {
        userId: membership.userId,
        role: roleSlug,
        status: membership.status,
      });

      // Fetch full user details if we have userId
      if (membership.userId) {
        try {
          const user = await workos.userManagement.getUser(membership.userId);
          logger.info(`Fetched user ${membership.userId}`, {
            email: user.email,
            firstName: user.firstName,
            lastName: user.lastName,
            role: roleSlug,
          });
          if (user.email) {
            userEmails.push(user.email);
          }
        } catch (userError) {
          logger.warn(`Could not fetch user ${membership.userId}`, { userError });
        }
      }
    }

    logger.info(`All role slugs found in organization: ${Array.from(allRoles).join(', ')}`);
    logger.info(`Returning ${userEmails.length} user emails for organization ${workosOrgId}`);
    return userEmails;
  } catch (error) {
    logger.error(`Failed to fetch organization memberships for ${workosOrgId}`, { error });
    return [];
  }
}

async function backfillNotionCRM(
  dryRun: boolean = false,
  tenantId?: string,
  startDate?: Date,
  skipFreeEmailDomains: boolean = false
): Promise<void> {
  logger.info('Starting Notion CRM backfill', {
    dryRun,
    tenantId,
    startDate: startDate?.toISOString(),
    skipFreeEmailDomains,
  });

  const stats: BackfillStats = {
    totalTenants: 0,
    provisioned: 0,
    notProvisioned: 0,
    created: 0,
    updated: 0,
    failed: 0,
    skipped: 0,
  };

  try {
    // Ensure all required Notion properties exist
    if (!dryRun) {
      logger.info('Ensuring all required Notion CRM properties exist...');
      const propertiesEnsured = await ensureNotionProperties();
      if (!propertiesEnsured) {
        logger.error('Failed to ensure Notion properties, continuing anyway...');
      }
    } else {
      logger.info('DRY RUN - Skipping property check');
    }

    // Fetch tenants from control database
    if (tenantId) {
      logger.info(`Fetching specific tenant: ${tenantId}`);
    } else if (startDate) {
      logger.info(`Fetching tenants created on or after ${startDate.toISOString()}...`);
    } else {
      logger.info('Fetching all tenants from control database...');
    }
    const tenants = await getAllTenants(tenantId, startDate);
    stats.totalTenants = tenants.length;

    if (tenants.length === 0) {
      logger.warn(
        tenantId
          ? `Tenant ${tenantId} not found`
          : startDate
            ? `No tenants found created on or after ${startDate.toISOString()}`
            : 'No tenants found'
      );
      return;
    }

    logger.info(`Found ${tenants.length} tenant${tenants.length === 1 ? '' : 's'}`);

    // Process each tenant
    for (const tenant of tenants) {
      logger.info(`Processing tenant ${tenant.id}`, {
        tenantId: tenant.id,
        workosOrgId: tenant.workos_org_id,
        state: tenant.state,
      });

      // Track provisioning state
      if (tenant.state === 'provisioned') {
        stats.provisioned++;
      } else {
        stats.notProvisioned++;
      }

      // Only process provisioned tenants
      if (tenant.state !== 'provisioned') {
        logger.info(`Skipping tenant ${tenant.id} - not provisioned (state: ${tenant.state})`);
        stats.skipped++;
        continue;
      }

      // Fetch organization details from WorkOS
      logger.info(`Fetching organization details from WorkOS for ${tenant.workos_org_id}`);
      const organization = await getOrganizationDetails(tenant.workos_org_id);

      if (!organization) {
        logger.warn(`Could not fetch organization ${tenant.workos_org_id} from WorkOS - skipping`);
        stats.skipped++;
        continue;
      }

      // Fetch user emails from organization
      logger.info(`Fetching user emails for organization ${organization.id}`);
      const adminEmails = await getOrganizationAdminEmails(organization.id);
      logger.info(`Found ${adminEmails.length} user emails for tenant ${tenant.id}`, {
        emails: adminEmails,
      });

      // Skip organizations with only free email domains if flag is set
      if (skipFreeEmailDomains && hasOnlyFreeEmailDomains(adminEmails)) {
        logger.info(`Skipping tenant ${tenant.id} - all admin emails are from free email domains`, {
          emails: adminEmails,
        });
        stats.skipped++;
        continue;
      }

      // Check integration status for this tenant
      logger.info(`Checking integration status for tenant ${tenant.id}`);
      const integrationStatus = await checkIntegrationStatus(tenant.id);

      // Count configured integrations
      const configuredIntegrations = Object.entries(integrationStatus).filter(
        ([_, isConfigured]) => isConfigured
      );

      logger.info(
        `Tenant ${tenant.id} has ${configuredIntegrations.length} integrations configured`,
        {
          integrations: configuredIntegrations.map(([name]) => name),
        }
      );

      // Prepare customer record data
      const customerData: CustomerRecordData = {
        tenantId: tenant.id,
        workosOrgId: tenant.workos_org_id,
        orgName: organization.name,
        adminEmails,
        createdAt: tenant.created_at,
        onboardedAt: tenant.provisioned_at,
      };

      if (dryRun) {
        // Check if record already exists
        const existingPageId = await findPageIdForTenant(tenant.id);
        const action = existingPageId ? 'update' : 'create';

        logger.info(`DRY RUN - Would ${action} Notion record:`, {
          tenantId: customerData.tenantId,
          workosOrgId: customerData.workosOrgId,
          orgName: customerData.orgName,
          adminEmails: customerData.adminEmails,
          adminCount: customerData.adminEmails.length,
          createdAt: customerData.createdAt?.toISOString(),
          onboardedAt: customerData.onboardedAt?.toISOString() || null,
          slackConfigured: integrationStatus.slack,
          integrations: configuredIntegrations.map(([name]) => name),
          existingPageId,
          action,
        });

        if (existingPageId) {
          stats.updated++;
        } else {
          stats.created++;
        }
      } else {
        // Check if record already exists
        logger.info(`Checking if Notion record exists for tenant ${tenant.id}`);
        const existingPageId = await findPageIdForTenant(tenant.id);

        let success = false;
        if (existingPageId) {
          // Update existing record
          logger.info(`Updating existing Notion CRM record for tenant ${tenant.id}`, {
            pageId: existingPageId,
          });
          success = await updateCustomerRecord(existingPageId, customerData);

          if (success) {
            logger.info(`✅ Successfully updated Notion record for tenant ${tenant.id}`);
            stats.updated++;
          }
        } else {
          // Create new record
          logger.info(`Creating new Notion CRM record for tenant ${tenant.id}`);
          success = await createCustomerRecord(customerData);

          if (success) {
            logger.info(`✅ Successfully created Notion record for tenant ${tenant.id}`);
            stats.created++;
          }
        }

        if (success) {
          // Update Slack bot status if configured
          if (integrationStatus.slack) {
            logger.info(`Updating Slack bot status for tenant ${tenant.id}`);
            await updateSlackBotStatus(tenant.id, true);
          }

          // Update integration statuses
          const integrationMapping = {
            slack: 'slack',
            github: 'github',
            notion: 'notion',
            linear: 'linear',
            googleDrive: 'google-drive',
            googleEmail: 'google-email',
            salesforce: 'salesforce',
            hubspot: 'hubspot',
            jira: 'jira',
            confluence: 'confluence',
          };

          for (const [key, integrationId] of Object.entries(integrationMapping)) {
            if (integrationStatus[key as keyof IntegrationStatus]) {
              logger.info(`Updating ${integrationId} status for tenant ${tenant.id}`);
              await updateIntegrationStatus(tenant.id, integrationId, true);
            }
          }

          logger.info(
            `✅ Updated integration statuses for tenant ${tenant.id} (${configuredIntegrations.length} integrations)`
          );
        } else {
          logger.error(`❌ Failed to create/update Notion record for tenant ${tenant.id}`);
          stats.failed++;
        }
      }

      // Add a small delay to avoid rate limiting
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    // Print summary
    logger.info('='.repeat(80));
    logger.info('Backfill Summary:');
    logger.info(`  Total tenants: ${stats.totalTenants}`);
    logger.info(`  Provisioned: ${stats.provisioned}`);
    logger.info(`  Not provisioned: ${stats.notProvisioned}`);
    logger.info(`  Skipped: ${stats.skipped}`);
    logger.info(`  Created: ${stats.created}`);
    logger.info(`  Updated: ${stats.updated}`);
    logger.info(`  Failed: ${stats.failed}`);
    logger.info('='.repeat(80));

    if (dryRun) {
      logger.info('DRY RUN - No records were actually created');
    }
  } catch (error) {
    logger.error('Fatal error during backfill', { error });
    throw error;
  } finally {
    // Close database connection
    await closeControlDbPool();
  }
}

// Main execution
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const skipFreeEmailDomains = args.includes('--skip-free-email-domains');

// Parse tenant ID flag
let tenantId: string | undefined;
const tenantIdFlagIndex = args.findIndex((arg) => arg === '--tenant-id');
if (tenantIdFlagIndex !== -1 && args[tenantIdFlagIndex + 1]) {
  tenantId = args[tenantIdFlagIndex + 1];
}

// Parse start date flag
let startDate: Date | undefined;
const startDateFlagIndex = args.findIndex((arg) => arg === '--start-date');
if (startDateFlagIndex !== -1 && args[startDateFlagIndex + 1]) {
  const dateString = args[startDateFlagIndex + 1];
  startDate = new Date(dateString);

  // Validate the date
  if (isNaN(startDate.getTime())) {
    console.error(`❌ Invalid date format: ${dateString}`);
    console.error('Expected ISO 8601 format: YYYY-MM-DD (e.g., 2025-01-01)');
    process.exit(1);
  }
}

if (dryRun) {
  console.log('🔍 Running in DRY RUN mode - no records will be created\n');
}

if (tenantId) {
  console.log(`🎯 Running for specific tenant: ${tenantId}\n`);
}

if (startDate) {
  console.log(
    `📅 Filtering tenants created on or after: ${startDate.toISOString().split('T')[0]}\n`
  );
}

if (skipFreeEmailDomains) {
  console.log('🚫 Skipping organizations with only free email domains\n');
}

backfillNotionCRM(dryRun, tenantId, startDate, skipFreeEmailDomains)
  .then(() => {
    logger.info('Backfill completed successfully');
    process.exit(0);
  })
  .catch((error) => {
    logger.error('Backfill failed', { error });
    process.exit(1);
  });
