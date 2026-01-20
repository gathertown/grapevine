/**
 * Marketing HubSpot Company Service
 *
 * Manages company creation and updates in Grapevine's marketing HubSpot account.
 * Companies represent Grapevine organizations/tenants and track onboarding progress.
 * This is for tracking our customers' onboarding, NOT for customer data integration.
 */

import {
  getMarketingHubSpotClient,
  isMarketingHubSpotEnabled,
} from '../../marketing-hubspot-client.js';
import { logger } from '../../utils/logger.js';
import {
  SimplePublicObjectInputForCreate,
  FilterOperatorEnum,
} from '@hubspot/api-client/lib/codegen/crm/companies/index.js';

export interface CompanyProperties {
  [key: string]: string | number | boolean;
}

export interface CreateCompanyResult {
  success: boolean;
  companyId?: string;
  error?: string;
}

export interface UpdateCompanyResult {
  success: boolean;
  error?: string;
}

/**
 * Create or update a company in marketing HubSpot
 * Uses tenant_id as the unique identifier
 */
export async function createOrUpdateMarketingCompany(
  companyName: string,
  tenantId: string,
  properties: CompanyProperties
): Promise<CreateCompanyResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping company creation', {
      companyName,
      tenantId,
    });
    return { success: true }; // Return success to not block user flows
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', { companyName, tenantId });
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    // Check if company exists
    const existingCompany = await findCompanyByTenantId(tenantId);

    if (existingCompany) {
      // Update existing company
      logger.info('Updating existing marketing HubSpot company', {
        companyName,
        tenantId,
        companyId: existingCompany,
      });

      // Convert properties to string values for HubSpot API
      const updateProperties: Record<string, string> = Object.entries({
        name: companyName,
        ...properties,
      }).reduce<Record<string, string>>((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
      }, {});

      await client.crm.companies.basicApi.update(existingCompany, {
        properties: updateProperties,
      });

      return { success: true, companyId: existingCompany };
    } else {
      // Create new company
      logger.info('Creating new marketing HubSpot company', { companyName, tenantId });

      // Convert properties to string values for HubSpot API
      const companyProperties: Record<string, string> = Object.entries({
        name: companyName,
        tenant_id: tenantId,
        ...properties,
      }).reduce<Record<string, string>>((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
      }, {});

      const companyInput: SimplePublicObjectInputForCreate = {
        properties: companyProperties,
      };

      const result = await client.crm.companies.basicApi.create(companyInput);

      logger.info('Marketing HubSpot company created successfully', {
        companyName,
        tenantId,
        companyId: result.id,
      });

      return { success: true, companyId: result.id };
    }
  } catch (error) {
    logger.error('Failed to create or update marketing HubSpot company', error, {
      companyName,
      tenantId,
    });
    return { success: false, error: String(error) };
  }
}

/**
 * Update specific properties on an existing company
 * Provide either tenantId OR companyId (not both)
 */
export async function updateMarketingCompanyProperties(
  properties: CompanyProperties,
  options: { tenantId?: string; companyId?: string }
): Promise<UpdateCompanyResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping company property update', options);
    return { success: true };
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', options);
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    let companyId: string;

    if (options.companyId) {
      // Direct company ID provided
      companyId = options.companyId;
    } else if (options.tenantId) {
      // Tenant ID provided - need to look up company ID
      const foundCompanyId = await findCompanyByTenantId(options.tenantId);
      if (!foundCompanyId) {
        logger.warn('Company not found in marketing HubSpot, cannot update properties', {
          tenantId: options.tenantId,
        });
        return { success: false, error: 'Company not found' };
      }
      companyId = foundCompanyId;
    } else {
      logger.warn('Must provide either tenantId or companyId');
      return { success: false, error: 'Must provide either tenantId or companyId' };
    }

    // Convert properties to string values for HubSpot API
    const updateProperties: Record<string, string> = Object.entries(properties).reduce<
      Record<string, string>
    >((acc, [key, value]) => {
      acc[key] = String(value);
      return acc;
    }, {});

    await client.crm.companies.basicApi.update(companyId, {
      properties: updateProperties,
    });

    logger.info('Marketing HubSpot company properties updated', {
      companyId,
      properties: Object.keys(properties),
    });

    return { success: true };
  } catch (error) {
    logger.error('Failed to update marketing HubSpot company properties', error, options);
    return { success: false, error: String(error) };
  }
}

/**
 * Find a company by tenant_id
 * Returns the company ID if found, null otherwise
 */
async function findCompanyByTenantId(tenantId: string): Promise<string | null> {
  const client = getMarketingHubSpotClient();
  if (!client) {
    return null;
  }

  try {
    const searchResults = await client.crm.companies.searchApi.doSearch({
      filterGroups: [
        {
          filters: [
            {
              propertyName: 'tenant_id',
              operator: FilterOperatorEnum.Eq,
              value: tenantId,
            },
          ],
        },
      ],
      properties: ['tenant_id', 'name'],
      limit: 1,
    });

    if (searchResults.results && searchResults.results.length > 0 && searchResults.results[0]) {
      return searchResults.results[0].id;
    }

    return null;
  } catch (error) {
    logger.error('Error searching for company by tenant_id in marketing HubSpot', error, {
      tenantId,
    });
    return null;
  }
}

/**
 * Get company properties by tenant_id
 */
export async function getMarketingCompanyProperties(
  tenantId: string,
  propertyNames: string[]
): Promise<CompanyProperties | null> {
  if (!isMarketingHubSpotEnabled()) {
    return null;
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    return null;
  }

  try {
    const companyId = await findCompanyByTenantId(tenantId);
    if (!companyId) {
      return null;
    }

    const company = await client.crm.companies.basicApi.getById(companyId, propertyNames);

    return (company.properties as CompanyProperties) || null;
  } catch (error) {
    logger.error('Failed to get marketing HubSpot company properties', error, { tenantId });
    return null;
  }
}

/**
 * Get company ID by tenant_id (public version for associations)
 */
export async function getCompanyIdByTenantId(tenantId: string): Promise<string | null> {
  return findCompanyByTenantId(tenantId);
}

/**
 * Update Slackbot configuration status for a company
 */
export async function updateSlackbotConfigured(
  tenantId: string,
  configured: boolean
): Promise<UpdateCompanyResult> {
  return updateMarketingCompanyProperties(
    {
      grapevine_slackbot_configured: configured,
    },
    { tenantId }
  );
}
