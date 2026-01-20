/**
 * Marketing HubSpot Contact Service
 *
 * Manages contact creation and updates in Grapevine's marketing HubSpot account.
 * This is for tracking our customers' onboarding progress, NOT for customer data integration.
 */

import {
  getMarketingHubSpotClient,
  isMarketingHubSpotEnabled,
} from '../../marketing-hubspot-client.js';
import { logger } from '../../utils/logger.js';
import {
  SimplePublicObjectInputForCreate,
  FilterOperatorEnum,
} from '@hubspot/api-client/lib/codegen/crm/contacts/index.js';

export interface ContactProperties {
  [key: string]: string | number | boolean;
}

export interface CreateContactResult {
  success: boolean;
  contactId?: string;
  error?: string;
}

export interface UpdateContactResult {
  success: boolean;
  error?: string;
}

/**
 * Create or update a contact in marketing HubSpot
 * Uses email as the unique identifier
 */
export async function createOrUpdateMarketingContact(
  email: string,
  properties: ContactProperties
): Promise<CreateContactResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping contact creation', { email });
    return { success: true }; // Return success to not block user flows
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', { email });
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    // Check if contact exists
    const existingContact = await findContactByEmail(email);

    if (existingContact) {
      // Update existing contact
      logger.info('Updating existing marketing HubSpot contact', {
        email,
        contactId: existingContact,
      });

      // Convert properties to string values for HubSpot API
      const updateProperties: Record<string, string> = Object.entries({
        email,
        ...properties,
      }).reduce<Record<string, string>>((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
      }, {});

      await client.crm.contacts.basicApi.update(existingContact, {
        properties: updateProperties,
      });

      return { success: true, contactId: existingContact };
    } else {
      // Create new contact
      logger.info('Creating new marketing HubSpot contact', { email });

      // Convert properties to string values for HubSpot API
      const contactProperties: Record<string, string> = Object.entries({
        email,
        ...properties,
      }).reduce<Record<string, string>>((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
      }, {});

      const contactInput: SimplePublicObjectInputForCreate = {
        properties: contactProperties,
      };

      const result = await client.crm.contacts.basicApi.create(contactInput);

      logger.info('Marketing HubSpot contact created successfully', {
        email,
        contactId: result.id,
      });

      return { success: true, contactId: result.id };
    }
  } catch (error) {
    logger.error('Failed to create or update marketing HubSpot contact', error, { email });
    return { success: false, error: String(error) };
  }
}

/**
 * Update specific properties on an existing contact
 */
export async function updateMarketingContactProperties(
  email: string,
  properties: ContactProperties
): Promise<UpdateContactResult> {
  if (!isMarketingHubSpotEnabled()) {
    logger.debug('Marketing HubSpot is disabled, skipping property update', { email });
    return { success: true };
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    logger.warn('Marketing HubSpot client not available', { email });
    return { success: false, error: 'HubSpot client not configured' };
  }

  try {
    const contactId = await findContactByEmail(email);

    if (!contactId) {
      logger.warn('Contact not found in marketing HubSpot, cannot update properties', { email });
      return { success: false, error: 'Contact not found' };
    }

    await client.crm.contacts.basicApi.update(contactId, {
      properties: properties as Record<string, string>,
    });

    logger.info('Marketing HubSpot contact properties updated', {
      email,
      contactId,
      properties: Object.keys(properties),
    });

    return { success: true };
  } catch (error) {
    logger.error('Failed to update marketing HubSpot contact properties', error, { email });
    return { success: false, error: String(error) };
  }
}

/**
 * Find a contact by email address
 * Returns the contact ID if found, null otherwise
 */
async function findContactByEmail(email: string): Promise<string | null> {
  const client = getMarketingHubSpotClient();
  if (!client) {
    return null;
  }

  try {
    const searchResults = await client.crm.contacts.searchApi.doSearch({
      filterGroups: [
        {
          filters: [
            {
              propertyName: 'email',
              operator: FilterOperatorEnum.Eq,
              value: email,
            },
          ],
        },
      ],
      properties: ['email'],
      limit: 1,
    });

    if (searchResults.results && searchResults.results.length > 0 && searchResults.results[0]) {
      return searchResults.results[0].id;
    }

    return null;
  } catch (error) {
    logger.error('Error searching for contact by email in marketing HubSpot', error, { email });
    return null;
  }
}

/**
 * Get contact properties by email
 */
export async function getMarketingContactProperties(
  email: string,
  propertyNames: string[]
): Promise<ContactProperties | null> {
  if (!isMarketingHubSpotEnabled()) {
    return null;
  }

  const client = getMarketingHubSpotClient();
  if (!client) {
    return null;
  }

  try {
    const contactId = await findContactByEmail(email);
    if (!contactId) {
      return null;
    }

    const contact = await client.crm.contacts.basicApi.getById(contactId, propertyNames);

    return (contact.properties as ContactProperties) || null;
  } catch (error) {
    logger.error('Failed to get marketing HubSpot contact properties', error, { email });
    return null;
  }
}
