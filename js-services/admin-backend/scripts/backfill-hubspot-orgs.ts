/**
 * Backfill HubSpot Organizations Script
 *
 * This script syncs existing organizations from WorkOS and the control database
 * to the marketing HubSpot account. It creates company records and associates
 * the first admin user of each organization as a contact.
 *
 * Usage:
 *   npx tsx scripts/backfill-hubspot-orgs.ts [--dry-run]
 *
 * Options:
 *   --dry-run: Show what would be done without making actual changes
 */

import { getWorkOSClient } from '../src/workos-client.js';
import { getControlDbPool } from '../src/control-db.js';
import { createContactAndBackfillCompany } from '../src/services/marketing-hubspot/association.service.js';
import { updateSlackbotConfigured } from '../src/services/marketing-hubspot/company.service.js';
import { getConfigValue } from '../src/config/index.js';
import { logger } from '../src/utils/logger.js';

interface TenantData {
  tenantId: string;
  workosOrgId: string;
  state: string;
  billingMode: 'grapevine_managed' | 'gather_managed';
}

interface OrganizationData {
  tenantId: string;
  workosOrgId: string;
  orgName: string;
  billingMode: 'grapevine_managed' | 'gather_managed';
  adminEmail?: string;
  adminFirstName?: string;
  adminLastName?: string;
}

async function getAllTenants(): Promise<TenantData[]> {
  const pool = getControlDbPool();
  if (!pool) {
    throw new Error('Control database not available');
  }

  const result = await pool.query<TenantData>(
    `SELECT id as "tenantId", workos_org_id as "workosOrgId", state, billing_mode as "billingMode"
     FROM public.tenants
     WHERE state = 'provisioned' AND deleted_at IS NULL
     ORDER BY created_at ASC`
  );

  return result.rows;
}

async function getOrganizationWithAdmin(tenant: TenantData): Promise<OrganizationData | null> {
  const { workosOrgId, tenantId } = tenant;
  const workos = getWorkOSClient();
  if (!workos) {
    throw new Error('WorkOS client not available');
  }

  try {
    // Get organization details
    const organization = await workos.organizations.getOrganization(workosOrgId);

    // Get organization memberships to find an admin
    const memberships = await workos.userManagement.listOrganizationMemberships({
      organizationId: workosOrgId,
      limit: 100,
    });

    // Find first admin user
    const adminMembership = memberships.data.find((m) => m.role?.slug === 'admin');

    let adminEmail: string | undefined;
    let adminFirstName: string | undefined;
    let adminLastName: string | undefined;

    if (adminMembership) {
      try {
        const user = await workos.userManagement.getUser(adminMembership.userId);
        adminEmail = user.email;
        adminFirstName = user.firstName ?? undefined;
        adminLastName = user.lastName ?? undefined;
      } catch (error) {
        logger.warn(`Could not fetch user details for admin of org ${workosOrgId}`, { error });
      }
    }

    return {
      tenantId,
      workosOrgId,
      orgName: organization.name,
      billingMode: tenant.billingMode,
      adminEmail,
      adminFirstName,
      adminLastName,
    };
  } catch (error) {
    logger.error(`Failed to fetch organization ${workosOrgId}`, { error });
    return null;
  }
}

async function syncOrganizationToHubSpot(
  orgData: OrganizationData,
  dryRun: boolean
): Promise<boolean> {
  logger.info(`Processing organization: ${orgData.orgName}`, {
    tenantId: orgData.tenantId,
    workosOrgId: orgData.workosOrgId,
    adminEmail: orgData.adminEmail,
  });

  if (dryRun) {
    logger.info('DRY RUN: Would create/update contact and backfill company', {
      orgName: orgData.orgName,
      tenantId: orgData.tenantId,
      adminEmail: orgData.adminEmail,
    });

    return true;
  }

  // Skip if no admin email
  if (!orgData.adminEmail) {
    logger.info('No admin email found, skipping HubSpot sync', {
      orgName: orgData.orgName,
      tenantId: orgData.tenantId,
    });
    return true;
  }

  // Create contact properties
  const contactProperties: Record<string, string> = {};
  if (orgData.adminFirstName) {
    contactProperties.firstname = orgData.adminFirstName;
  }
  if (orgData.adminLastName) {
    contactProperties.lastname = orgData.adminLastName;
  }

  // Create contact and let HubSpot auto-associate with company, then backfill properties
  const result = await createContactAndBackfillCompany(
    orgData.adminEmail,
    orgData.tenantId,
    orgData.orgName,
    contactProperties,
    orgData.billingMode
  );

  if (!result.success) {
    logger.error(`Failed to create contact and backfill company in HubSpot`, {
      orgName: orgData.orgName,
      tenantId: orgData.tenantId,
      error: result.error,
    });
    return false;
  }

  logger.info('Contact and company synced successfully to HubSpot', {
    orgName: orgData.orgName,
    tenantId: orgData.tenantId,
    contactId: result.contactId,
    companyId: result.companyId,
  });

  // Check if Slackbot is configured and update HubSpot if so
  try {
    const slackBotToken = await getConfigValue('SLACK_BOT_TOKEN', orgData.tenantId);
    if (slackBotToken && typeof slackBotToken === 'string' && result.companyId) {
      logger.info(`Updating Slackbot status for tenant ${orgData.tenantId}`);
      await updateSlackbotConfigured(orgData.tenantId, true);
      logger.info('Slackbot status updated in HubSpot', {
        tenantId: orgData.tenantId,
        companyId: result.companyId,
      });
    }
  } catch (error) {
    logger.warn('Failed to update Slackbot status in HubSpot', {
      error,
      tenantId: orgData.tenantId,
    });
  }

  return true;
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');

  if (dryRun) {
    logger.info('🏃 Running in DRY RUN mode - no changes will be made');
  }

  logger.info('Starting HubSpot organizations backfill...');

  try {
    // Get all provisioned tenants
    const tenants = await getAllTenants();
    logger.info(`Found ${tenants.length} provisioned tenants to process`);

    let successCount = 0;
    let failureCount = 0;
    let skippedCount = 0;

    // Process each tenant
    for (const tenant of tenants) {
      try {
        const orgData = await getOrganizationWithAdmin(tenant);

        if (!orgData) {
          logger.warn(`Skipping tenant ${tenant.tenantId} - could not fetch organization data`);
          skippedCount++;
          continue;
        }

        const success = await syncOrganizationToHubSpot(orgData, dryRun);

        if (success) {
          successCount++;
        } else {
          failureCount++;
        }

        // Small delay to avoid rate limiting
        await new Promise((resolve) => setTimeout(resolve, 500));
      } catch (error) {
        logger.error(`Error processing tenant ${tenant.tenantId}`, { error });
        failureCount++;
      }
    }

    logger.info('Backfill complete!', {
      total: tenants.length,
      success: successCount,
      failed: failureCount,
      skipped: skippedCount,
    });

    process.exit(failureCount > 0 ? 1 : 0);
  } catch (error) {
    logger.error('Fatal error during backfill', { error });
    process.exit(1);
  }
}

// Run the script
main().catch((error) => {
  logger.error('Unhandled error in backfill script', { error });
  process.exit(1);
});
