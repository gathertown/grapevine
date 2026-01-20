/**
 * Marketing HubSpot Association Service
 *
 * Manages associations between contacts and companies in Grapevine's marketing HubSpot account.
 * This allows multiple contacts (users) to be linked to a single company (organization/tenant).
 */

import {
  getMarketingHubSpotClient,
  isMarketingHubSpotEnabled,
} from '../../marketing-hubspot-client.js';
import { logger } from '../../utils/logger.js';
import { createOrUpdateMarketingContact, type ContactProperties } from './contact.service.js';
import {
  getCompanyIdByTenantId,
  updateMarketingCompanyProperties,
  createOrUpdateMarketingCompany,
} from './company.service.js';
import { AssociationSpecAssociationCategoryEnum } from '@hubspot/api-client/lib/codegen/crm/associations/v4/index.js';

export interface AssociationResult {
  success: boolean;
  error?: string;
}

export interface CreateContactWithCompanyResult {
  success: boolean;
  contactId?: string;
  companyId?: string;
  error?: string;
}

/**
 * Associate a contact to a company in marketing HubSpot
 * Uses the predefined "contact_to_company" association type
 */
export async function associateContactToCompany(
  contactId: string,
  companyId: string
): Promise<AssociationResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping contact-company association', {
      contactId,
      companyId,
    });
    return { success: true };
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', { contactId, companyId });
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    logger.info('Associating contact to company in marketing HubSpot', {
      contactId,
      companyId,
    });

    // Use the standard contact-to-company association type
    // Association type ID 1 is "Primary" company for contacts in HubSpot v4 API
    // (the v4 API uses different type IDs than v3)
    await client.crm.associations.v4.basicApi.create(
      'contacts',
      contactId,
      'companies',
      companyId,
      [
        {
          associationCategory: AssociationSpecAssociationCategoryEnum.HubspotDefined,
          associationTypeId: 1, // Primary company association for contacts
        },
      ]
    );

    logger.info('Contact associated to company successfully', {
      contactId,
      companyId,
    });

    return { success: true };
  } catch (error) {
    logger.error('Failed to associate contact to company', error, {
      contactId,
      companyId,
    });
    return { success: false, error: String(error) };
  }
}

/**
 * Create or update a contact and associate it to a company by tenant_id
 * This is a convenience function for the common workflow of creating a contact
 * and linking it to an organization's company record
 *
 * @param companyId - Optional company ID to use directly (avoids search delay issues)
 */
export async function createContactWithCompany(
  email: string,
  tenantId: string,
  contactProperties?: ContactProperties,
  companyId?: string
): Promise<CreateContactWithCompanyResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping contact creation with company', {
      email,
      tenantId,
    });
    return { success: true };
  }

  try {
    logger.info('Creating contact with company association', {
      email,
      tenantId,
      companyId,
    });

    // Get the company ID - either use provided one or search for it
    let resolvedCompanyId: string;
    if (companyId) {
      resolvedCompanyId = companyId;
    } else {
      const foundCompanyId = await getCompanyIdByTenantId(tenantId);
      if (!foundCompanyId) {
        logger.warn('Company not found for tenant, cannot create contact association', {
          email,
          tenantId,
        });
        return { success: false, error: 'Company not found for tenant' };
      }
      resolvedCompanyId = foundCompanyId;
    }

    // Create or update the contact
    const contactResult = await createOrUpdateMarketingContact(email, contactProperties || {});
    if (!contactResult.success) {
      return {
        success: false,
        error: contactResult.error || 'Failed to create contact',
      };
    }

    // Associate the contact to the company
    if (contactResult.contactId) {
      const associationResult = await associateContactToCompany(
        contactResult.contactId,
        resolvedCompanyId
      );

      if (!associationResult.success) {
        logger.warn('Contact created but association failed', {
          email,
          tenantId,
          contactId: contactResult.contactId,
          companyId: resolvedCompanyId,
        });
        // Return success for contact creation even if association fails
        // The contact exists and can be manually associated later
      }
    }

    logger.info('Contact created and associated to company successfully', {
      email,
      tenantId,
      contactId: contactResult.contactId,
      companyId: resolvedCompanyId,
    });

    return {
      success: true,
      contactId: contactResult.contactId,
      companyId: resolvedCompanyId,
    };
  } catch (error) {
    logger.error('Failed to create contact with company association', error, {
      email,
      tenantId,
    });
    return { success: false, error: String(error) };
  }
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
  ];

  return freeEmailDomains.includes(domain);
}

/**
 * Create contact and let HubSpot auto-associate with company based on email domain,
 * then backfill the company with Grapevine properties
 *
 * This leverages HubSpot's built-in domain extraction and company matching logic
 *
 * Skips free email domains (gmail, hotmail, etc.)
 */
export async function createContactAndBackfillCompany(
  email: string,
  tenantId: string,
  organizationName: string,
  contactProperties?: ContactProperties,
  billingMode?: 'grapevine_managed' | 'gather_managed'
): Promise<CreateContactWithCompanyResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping contact and company creation', {
      email,
      tenantId,
    });
    return { success: true };
  }

  // Skip free email domains
  if (isFreeEmailDomain(email)) {
    logger.info('Skipping HubSpot sync for free email domain', {
      email,
      tenantId,
    });
    return { success: true };
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', { email, tenantId });
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    logger.info('Creating contact and backfilling company properties', {
      email,
      tenantId,
      organizationName,
    });

    // Step 1: Create or update the contact (HubSpot will auto-create/associate company from email domain)
    const contactPropertiesWithFlag = {
      is_grapevine_user: true,
      ...contactProperties,
    };
    const contactResult = await createOrUpdateMarketingContact(email, contactPropertiesWithFlag);
    if (!contactResult.success || !contactResult.contactId) {
      return {
        success: false,
        error: contactResult.error || 'Failed to create contact',
      };
    }

    logger.info('Contact created/updated successfully', {
      email,
      contactId: contactResult.contactId,
    });

    // Step 2: Retrieve associated companies for this contact
    const associations = await client.crm.associations.v4.basicApi.getPage(
      'contacts',
      contactResult.contactId,
      'companies'
    );

    let companyId: string | undefined;

    if (associations.results && associations.results.length > 0) {
      // HubSpot automatically associated the contact with a company based on email domain
      companyId = associations.results[0]?.toObjectId;

      logger.info('Found auto-associated company', {
        email,
        contactId: contactResult.contactId,
        companyId,
      });

      // Step 3: Backfill the company with Grapevine properties (but don't overwrite name)
      if (companyId) {
        const companyProperties: Record<string, string | boolean> = {
          tenant_id: tenantId,
        };

        // Add Gather onboarding flag if billing mode is gather_managed
        if (billingMode === 'gather_managed') {
          companyProperties.grapevine_onboarded_from_gather = true;
        }

        const updateResult = await updateMarketingCompanyProperties(companyProperties, {
          companyId,
        });

        if (!updateResult.success) {
          logger.warn('Failed to backfill company properties', {
            email,
            tenantId,
            companyId,
            error: updateResult.error,
          });
        } else {
          logger.info('Company properties backfilled successfully (name preserved)', {
            email,
            tenantId,
            companyId,
          });
        }
      }
    } else {
      // No auto-association - create company manually and associate it
      logger.info('No company auto-associated, creating company manually', {
        email,
        contactId: contactResult.contactId,
        organizationName,
      });

      const companyProperties: Record<string, string | boolean> = {};

      // Add Gather onboarding flag if billing mode is gather_managed
      if (billingMode === 'gather_managed') {
        companyProperties.grapevine_onboarded_from_gather = true;
      }

      const companyResult = await createOrUpdateMarketingCompany(
        organizationName,
        tenantId,
        companyProperties
      );

      if (companyResult.success && companyResult.companyId) {
        companyId = companyResult.companyId;

        // Associate the contact to the newly created company
        const associationResult = await associateContactToCompany(
          contactResult.contactId,
          companyId
        );

        if (!associationResult.success) {
          logger.warn('Company created but failed to associate with contact', {
            email,
            tenantId,
            contactId: contactResult.contactId,
            companyId,
            error: associationResult.error,
          });
        } else {
          logger.info('Company created and associated successfully', {
            email,
            tenantId,
            contactId: contactResult.contactId,
            companyId,
          });
        }
      } else {
        logger.warn('Failed to create company', {
          email,
          tenantId,
          error: companyResult.error,
        });
      }
    }

    return {
      success: true,
      contactId: contactResult.contactId,
      companyId,
    };
  } catch (error) {
    logger.error('Failed to create contact and backfill company', error, {
      email,
      tenantId,
    });
    return { success: false, error: String(error) };
  }
}
