/**
 * Control Database Connection
 *
 * This module provides connection utilities for the shared control database
 * used by the steward service for tenant provisioning coordination.
 */

import { Pool } from 'pg';
import { randomUUID } from 'node:crypto';
import { logger, LogContext } from './utils/logger';
import { createCustomerRecord } from './utils/notion-crm.js';
import { createContactAndBackfillCompany } from './services/marketing-hubspot/association.service.js';
import { Source } from '@corporate-context/shared-common';

let controlDbPool: Pool | null = null;

function getControlDatabaseUrl(): string | null {
  // Check environment variable
  if (process.env.CONTROL_DATABASE_URL) {
    return process.env.CONTROL_DATABASE_URL;
  }

  return null;
}

export function getControlDbPool(): Pool | null {
  if (controlDbPool) {
    return controlDbPool;
  }

  const databaseUrl = getControlDatabaseUrl();
  if (!databaseUrl) {
    logger.error(
      'Control database URL not configured. Set CONTROL_DATABASE_URL environment variable.'
    );
    return null;
  }

  const isLocalDb = databaseUrl.includes('localhost') || databaseUrl.includes('127.0.0.1');
  controlDbPool = new Pool({
    connectionString: databaseUrl,
    ssl: isLocalDb ? false : { rejectUnauthorized: false },
    max: 5,
    min: 1,
    connectionTimeoutMillis: 30000,
    idleTimeoutMillis: 30000,
    maxUses: 7500,
  });

  return controlDbPool;
}

export async function closeControlDbPool(): Promise<void> {
  if (controlDbPool) {
    await controlDbPool.end();
    controlDbPool = null;
  }
}

/**
 * Check if a tenant is deleted
 * @param tenantId - The tenant ID to check
 * @returns Promise<boolean> - True if tenant is deleted (deleted_at is not null), false otherwise
 */
export async function isTenantDeleted(tenantId: string): Promise<boolean> {
  return LogContext.run({ tenantId, operation: 'check-tenant-deleted' }, async () => {
    const pool = getControlDbPool();
    if (!pool) {
      logger.error('Control database not available for tenant deletion check');
      return false;
    }

    try {
      const result = await pool.query('SELECT deleted_at FROM tenants WHERE id = $1', [tenantId]);

      if (result.rows.length === 0) {
        logger.warn(`Tenant ${tenantId} not found in control database`);
        return false;
      }

      const deletedAt = result.rows[0].deleted_at;
      return deletedAt !== null;
    } catch (error) {
      logger.error(`Error checking tenant deletion status for ${tenantId}`, error);
      return false;
    }
  });
}

/**
 * Generate a 16 character tenant ID.
 * It's important that we don't include characters that can be problematic in a URL, like periods or underscores, in the tenant ID.
 * See https://gather-town.slack.com/archives/C08BMCZK81F/p1755036333301369
 */
function generateTenantId(): string {
  const uuid = randomUUID().replace(/-/g, '').toLowerCase();
  return uuid.substring(0, 16);
}

/**
 * Insert a new tenant into the control database for provisioning
 * Also handles CRM tracking in Notion and HubSpot if orgName and adminEmails are provided
 * @param workosOrgId - The WorkOS organization ID (external identifier)
 * @param billingMode - The billing mode for the tenant (defaults to 'grapevine_managed')
 * @param orgName - Optional organization name for CRM tracking
 * @param adminEmails - Optional admin email addresses for CRM tracking
 * @param adminFirstName - Optional first name for HubSpot contact
 * @param adminLastName - Optional last name for HubSpot contact
 * @param source - Optional source of the tenant ('landing_page' or 'docs')
 * @returns Object with success status and tenant ID if successful, or null if failed
 */
export async function createTenantProvisioningRequest(
  workosOrgId: string,
  billingMode: 'grapevine_managed' | 'gather_managed' = 'grapevine_managed',
  orgName?: string,
  adminEmails?: string[],
  adminFirstName?: string,
  adminLastName?: string,
  source?: Source
): Promise<{ tenantId: string } | null> {
  return LogContext.run(
    { workosOrgId, billingMode, operation: 'create-tenant-provisioning' },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for tenant provisioning request');
        return null;
      }

      try {
        const tenantId = generateTenantId();

        await pool.query(
          `INSERT INTO public.tenants (id, workos_org_id, state, billing_mode, source, created_at, updated_at)
           VALUES ($1, $2, 'pending', $3, $4, now(), now())`,
          [tenantId, workosOrgId, billingMode, source]
        );

        logger.info(`✅ Created tenant provisioning request for WorkOS org: ${workosOrgId}`, {
          tenantId,
          billingMode,
          source,
        });

        // Create Notion CRM record if we have orgName and adminEmails (fire and forget)
        if (orgName && adminEmails && adminEmails.length > 0) {
          createCustomerRecord({
            tenantId,
            workosOrgId,
            orgName,
            adminEmails,
          }).catch((error) => {
            logger.warn('Failed to create Notion CRM record', { error, tenantId });
          });
        }

        // Create HubSpot contact and company if we have all required data (fire and forget)
        if (orgName && adminEmails && adminEmails.length > 0 && adminEmails[0]) {
          const contactProperties: Record<string, string> = {};
          if (adminFirstName) {
            contactProperties.firstname = adminFirstName;
          }
          if (adminLastName) {
            contactProperties.lastname = adminLastName;
          }

          createContactAndBackfillCompany(
            adminEmails[0],
            tenantId,
            orgName,
            contactProperties,
            billingMode
          ).catch((error) => {
            logger.warn('Failed to create HubSpot contact and company', { error, tenantId });
          });
        }

        return { tenantId };
      } catch (error) {
        logger.error('Failed to create tenant provisioning request', error);
        return null;
      }
    }
  );
}

/**
 * Resolve WorkOS organization ID to internal tenant information
 * @param workosOrgId - The WorkOS organization ID (external identifier)
 * @returns Object with tenant ID, provisioning status, state, and error message, null if tenant doesn't exist
 * @throws Error if database operation fails
 */
export async function resolveWorkosOrgToTenant(workosOrgId: string): Promise<{
  tenantId: string;
  isProvisioned: boolean;
  state: string;
  errorMessage: string | null;
} | null> {
  return LogContext.run({ workosOrgId, operation: 'resolve-workos-org' }, async () => {
    const pool = getControlDbPool();
    if (!pool) {
      throw new Error('Control database not available for tenant resolution');
    }

    const result = await pool.query(
      `SELECT id, state, error_message FROM public.tenants
       WHERE workos_org_id = $1`,
      [workosOrgId]
    );

    if (result.rows.length > 0) {
      const tenantId = result.rows[0].id;
      const state = result.rows[0].state;
      const errorMessage = result.rows[0].error_message;
      const isProvisioned = state === 'provisioned';

      logger.info(`Found tenant ${tenantId} for WorkOS org ${workosOrgId}`, {
        tenant_id: tenantId,
        state,
        errorMessage,
      });
      return { tenantId, isProvisioned, state, errorMessage };
    }

    logger.info(`No tenant found for WorkOS org: ${workosOrgId}`);
    return null;
  });
}

/**
 * Look up tenant provisioning info by internal tenant ID
 * @param tenantId - The internal tenant identifier
 * @returns Object with tenant ID, provisioning status, state, and error message, null if tenant doesn't exist
 * @throws Error if database operation fails
 */
export async function getTenantInfoById(tenantId: string): Promise<{
  tenantId: string;
  isProvisioned: boolean;
  state: string;
  errorMessage: string | null;
} | null> {
  return LogContext.run({ tenantId, operation: 'get-tenant-by-id' }, async () => {
    const pool = getControlDbPool();
    if (!pool) {
      throw new Error('Control database not available for tenant lookup');
    }

    const result = await pool.query(
      `SELECT id, state, error_message FROM public.tenants
       WHERE id = $1`,
      [tenantId]
    );

    if (result.rows.length > 0) {
      const state = result.rows[0].state as string;
      const errorMessage = result.rows[0].error_message as string | null;
      const isProvisioned = state === 'provisioned';

      logger.info(`Found tenant ${tenantId}`, {
        tenant_id: tenantId,
        state,
        errorMessage,
      });
      return { tenantId, isProvisioned, state, errorMessage };
    }

    logger.info(`No tenant found for tenant id: ${tenantId}`);
    return null;
  });
}

/**
 * Resolve internal tenant ID to WorkOS organization ID
 * @param tenantId - The internal tenant identifier
 * @returns WorkOS organization ID if found, null if tenant doesn't exist
 * @throws Error if database operation fails
 */
export async function resolveTenantToWorkosOrg(tenantId: string): Promise<string | null> {
  return LogContext.run({ tenantId, operation: 'resolve-tenant-to-workos-org' }, async () => {
    const pool = getControlDbPool();
    if (!pool) {
      throw new Error('Control database not available for tenant-to-org resolution');
    }

    const result = await pool.query(
      `SELECT workos_org_id FROM public.tenants
       WHERE id = $1`,
      [tenantId]
    );

    if (result.rows.length > 0) {
      const workosOrgId = result.rows[0].workos_org_id as string;
      logger.info(`Resolved tenant ${tenantId} to WorkOS org ${workosOrgId}`, {
        tenant_id: tenantId,
        workos_org_id: workosOrgId,
      });
      return workosOrgId;
    }

    logger.info(`No WorkOS org found for tenant: ${tenantId}`);
    return null;
  });
}

/**
 * Update tenant Salesforce connection status
 * @param tenantId - The internal tenant identifier
 * @param hasConnection - Whether the tenant has Salesforce connected
 * @returns True if updated successfully, false otherwise
 * @throws Error if database operation fails
 */
export async function updateTenantHasSalesforceConnected(
  tenantId: string,
  hasConnection: boolean
): Promise<boolean> {
  return LogContext.run(
    { tenantId, hasConnection, operation: 'update-tenant-has-salesforce-connected' },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        throw new Error('Control database not available for Salesforce connection update');
      }

      try {
        await pool.query(`UPDATE public.tenants SET has_salesforce_connected = $1 WHERE id = $2`, [
          hasConnection,
          tenantId,
        ]);

        logger.info(`✅ Updated Salesforce connection status for tenant ${tenantId}`, {
          tenant_id: tenantId,
          has_salesforce_connected: hasConnection,
        });
        return true;
      } catch (error) {
        logger.error('Failed to update Salesforce connection status', error, {
          tenantId,
          hasConnection,
        });
        return false;
      }
    }
  );
}
