import { getNotionClient, getNotionDataSourceId, isNotionCrmEnabled } from '../clients/notion.js';
import { logger, LogContext } from './logger.js';

/**
 * Onboarding states
 */
export type OnboardingState = 'started' | 'onboarded' | 'churned';

/**
 * Required properties for the Notion CRM data source
 * Note: Title property is not included as it's created by default and cannot be added via API
 */
const REQUIRED_PROPERTIES = {
  'WorkOS Organization ID': {
    rich_text: {},
  },
  'Organization Name': {
    rich_text: {},
  },
  'Admin Emails': {
    rich_text: {},
  },
  'Onboarding State': {
    select: {
      options: [
        { name: 'started', color: 'yellow' },
        { name: 'onboarded', color: 'green' },
        { name: 'churned', color: 'red' },
      ],
    },
  },
  'Slack Bot Configured': {
    checkbox: {},
  },
  'First Integration Connected': {
    checkbox: {},
  },
  'Connected Integrations': {
    multi_select: {
      options: [
        { name: 'slack', color: 'purple' },
        { name: 'github', color: 'gray' },
        { name: 'notion', color: 'blue' },
        { name: 'linear', color: 'blue' },
        { name: 'google-drive', color: 'green' },
        { name: 'google-email', color: 'green' },
        { name: 'salesforce', color: 'blue' },
        { name: 'hubspot', color: 'orange' },
        { name: 'jira', color: 'blue' },
        { name: 'confluence', color: 'blue' },
      ],
    },
  },
  'Requested Integrations': {
    multi_select: {
      options: [
        { name: 'slack', color: 'purple' },
        { name: 'github', color: 'gray' },
        { name: 'notion', color: 'blue' },
        { name: 'linear', color: 'blue' },
        { name: 'google-drive', color: 'green' },
        { name: 'google-email', color: 'green' },
        { name: 'salesforce', color: 'blue' },
        { name: 'hubspot', color: 'orange' },
        { name: 'jira', color: 'blue' },
        { name: 'confluence', color: 'blue' },
      ],
    },
  },
  'Created At': {
    date: {},
  },
  'Last Activity': {
    date: {},
  },
  'Onboarded At': {
    date: {},
  },
  'Slack Notes': {
    rich_text: {},
  },
} as const;

/**
 * Ensure all required properties exist in the Notion data source
 * Creates any missing properties
 */
export async function ensureNotionProperties(): Promise<boolean> {
  return LogContext.run({ operation: 'notion-crm-ensure-properties' }, async () => {
    if (!isNotionCrmEnabled()) {
      logger.debug('Notion CRM not enabled, skipping property check');
      return false;
    }

    const client = getNotionClient();
    const dataSourceId = await getNotionDataSourceId();

    if (!client || !dataSourceId) {
      return false;
    }

    try {
      // Get current data source schema
      const dataSource = await client.request({
        path: `data_sources/${dataSourceId}`,
        method: 'get',
      });

      const existingProperties = (dataSource as Record<string, unknown>).properties || {};
      const existingPropertyNames = Object.keys(existingProperties);

      // Find missing properties
      const missingProperties: Record<string, Record<string, unknown>> = {};
      for (const [propName, propConfig] of Object.entries(REQUIRED_PROPERTIES)) {
        if (!existingPropertyNames.includes(propName)) {
          missingProperties[propName] = propConfig;
          logger.info(`Property "${propName}" missing, will create it`);
        }
      }

      // If there are missing properties, update the data source
      if (Object.keys(missingProperties).length > 0) {
        logger.info('Creating missing properties', {
          count: Object.keys(missingProperties).length,
          properties: Object.keys(missingProperties),
        });

        await client.request({
          path: `data_sources/${dataSourceId}`,
          method: 'patch',
          body: {
            properties: missingProperties,
          },
        });

        logger.info('✅ Successfully created missing properties');
      } else {
        logger.info('All required properties already exist');
      }

      return true;
    } catch (error) {
      logger.error('Failed to ensure Notion properties', error);
      return false;
    }
  });
}

/**
 * Customer record data for creation
 */
export interface CustomerRecordData {
  tenantId: string;
  workosOrgId: string;
  orgName: string;
  adminEmails: string[];
  createdAt?: Date;
  onboardedAt?: Date | null;
}

/**
 * Update an existing customer record in Notion CRM
 */
export async function updateCustomerRecord(
  pageId: string,
  data: CustomerRecordData
): Promise<boolean> {
  return LogContext.run({ operation: 'notion-crm-update', tenantId: data.tenantId }, async () => {
    if (!isNotionCrmEnabled()) {
      logger.debug('Notion CRM not enabled, skipping customer record update');
      return false;
    }

    const client = getNotionClient();

    if (!client) {
      return false;
    }

    try {
      logger.info('Updating Notion CRM record', {
        pageId,
        tenantId: data.tenantId,
        adminEmailsCount: data.adminEmails.length,
        adminEmails: data.adminEmails,
      });

      // Build properties object
      const properties: Record<string, unknown> = {
        // WorkOS Organization ID
        'WorkOS Organization ID': {
          rich_text: [
            {
              text: { content: data.workosOrgId },
            },
          ],
        },
        // Organization Name
        'Organization Name': {
          rich_text: [
            {
              text: { content: data.orgName },
            },
          ],
        },
        // Admin Emails - store as comma-separated list
        'Admin Emails': {
          rich_text: [
            {
              text: { content: data.adminEmails.join(', ') || '' },
            },
          ],
        },
        // Created At
        'Created At': {
          date: { start: (data.createdAt || new Date()).toISOString() },
        },
      };

      // Add Onboarded At if provided
      if (data.onboardedAt) {
        properties['Onboarded At'] = {
          date: { start: data.onboardedAt.toISOString() },
        };
      }

      await client.pages.update({
        page_id: pageId,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        properties: properties as any,
      });

      logger.info('✅ Updated Notion CRM customer record', {
        tenantId: data.tenantId,
        pageId,
      });

      return true;
    } catch (error) {
      logger.error('Failed to update Notion CRM customer record', error, {
        tenantId: data.tenantId,
        pageId,
      });
      return false;
    }
  });
}

/**
 * Create a new customer record in Notion CRM
 */
export async function createCustomerRecord(data: CustomerRecordData): Promise<boolean> {
  return LogContext.run({ operation: 'notion-crm-create', tenantId: data.tenantId }, async () => {
    if (!isNotionCrmEnabled()) {
      logger.debug('Notion CRM not enabled, skipping customer record creation');
      return false;
    }

    const client = getNotionClient();
    const dataSourceId = await getNotionDataSourceId();

    if (!client || !dataSourceId) {
      return false;
    }

    try {
      logger.info('Creating Notion CRM record', {
        tenantId: data.tenantId,
        adminEmailsCount: data.adminEmails.length,
        adminEmails: data.adminEmails,
      });

      // Build properties object
      const properties: Record<string, unknown> = {
        // Title property - Tenant ID
        'Tenant ID': {
          title: [
            {
              text: { content: data.tenantId },
            },
          ],
        },
        // WorkOS Organization ID
        'WorkOS Organization ID': {
          rich_text: [
            {
              text: { content: data.workosOrgId },
            },
          ],
        },
        // Organization Name
        'Organization Name': {
          rich_text: [
            {
              text: { content: data.orgName },
            },
          ],
        },
        // Admin Emails - store as comma-separated list
        'Admin Emails': {
          rich_text: [
            {
              text: { content: data.adminEmails.join(', ') || '' },
            },
          ],
        },
        // Onboarding State - started
        'Onboarding State': {
          select: { name: 'started' },
        },
        // Slack Bot Configured - false
        'Slack Bot Configured': {
          checkbox: false,
        },
        // First Integration Connected - false
        'First Integration Connected': {
          checkbox: false,
        },
        // Created At
        'Created At': {
          date: { start: (data.createdAt || new Date()).toISOString() },
        },
      };

      // Add Onboarded At if provided
      if (data.onboardedAt) {
        properties['Onboarded At'] = {
          date: { start: data.onboardedAt.toISOString() },
        };
      }

      const response = await client.pages.create({
        parent: { type: 'data_source_id', data_source_id: dataSourceId },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        properties: properties as any,
      });

      logger.info('✅ Created Notion CRM customer record', {
        tenantId: data.tenantId,
        pageId: response.id,
      });

      return true;
    } catch (error) {
      logger.error('Failed to create Notion CRM customer record', error, {
        tenantId: data.tenantId,
      });
      return false;
    }
  });
}

/**
 * Find Notion page ID for a tenant
 */
export async function findPageIdForTenant(tenantId: string): Promise<string | null> {
  const client = getNotionClient();
  const dataSourceId = await getNotionDataSourceId();

  if (!client || !dataSourceId) {
    return null;
  }

  try {
    // Query data source for page with matching tenant ID
    const response = await client.dataSources.query({
      data_source_id: dataSourceId,
      filter: {
        property: 'Tenant ID',
        title: {
          equals: tenantId,
        },
      },
    });

    if (response.results.length > 0) {
      const pageId = response.results[0]?.id;
      if (pageId) {
        return pageId;
      }
    }

    return null;
  } catch (error) {
    logger.error('Failed to find Notion page for tenant', error, { tenantId });
    return null;
  }
}

/**
 * Update Slack bot configuration status
 */
export async function updateSlackBotStatus(
  tenantId: string,
  configured: boolean
): Promise<boolean> {
  return LogContext.run(
    { operation: 'notion-crm-update-slack', tenantId, configured },
    async () => {
      if (!isNotionCrmEnabled()) {
        logger.debug('Notion CRM not enabled, skipping Slack bot status update');
        return false;
      }

      const pageId = await findPageIdForTenant(tenantId);
      if (!pageId) {
        logger.warn('Could not find Notion page for tenant', { tenantId });
        return false;
      }

      const client = getNotionClient();
      if (!client) {
        return false;
      }

      try {
        await client.pages.update({
          page_id: pageId,
          properties: {
            'Slack Bot Configured': {
              checkbox: configured,
            },
            'Last Activity': {
              date: { start: new Date().toISOString() },
            },
          },
        });

        logger.info('✅ Updated Slack bot status in Notion CRM', {
          tenantId,
          configured,
        });

        // If configured, add Slack to connected integrations
        if (configured) {
          await updateIntegrationStatus(tenantId, 'slack', true);
        }

        // Check if onboarding is complete
        await checkAndUpdateOnboardingState(tenantId);

        return true;
      } catch (error) {
        logger.error('Failed to update Slack bot status in Notion CRM', error, { tenantId });
        return false;
      }
    }
  );
}

/**
 * Track when a user requests an integration (e.g., clicks setup button)
 */
export async function trackIntegrationRequested(
  tenantId: string,
  integration: string
): Promise<boolean> {
  return LogContext.run(
    { operation: 'notion-crm-track-integration-requested', tenantId, integration },
    async () => {
      if (!isNotionCrmEnabled()) {
        logger.debug('Notion CRM not enabled, skipping integration request tracking');
        return false;
      }

      const pageId = await findPageIdForTenant(tenantId);
      if (!pageId) {
        logger.warn('Could not find Notion page for tenant', { tenantId });
        return false;
      }

      const client = getNotionClient();
      if (!client) {
        return false;
      }

      try {
        // Get current page to read existing requested integrations
        const page = await client.pages.retrieve({ page_id: pageId });

        // Extract current requested integrations
        const requestedIntegrations: string[] = [];
        if ('properties' in page) {
          const requestedProperty = page.properties['Requested Integrations'];
          if (requestedProperty && requestedProperty.type === 'multi_select') {
            requestedIntegrations.push(...requestedProperty.multi_select.map((item) => item.name));
          }
        }

        // Add integration if not already present
        if (!requestedIntegrations.includes(integration)) {
          requestedIntegrations.push(integration);

          // Update page
          await client.pages.update({
            page_id: pageId,
            properties: {
              'Requested Integrations': {
                multi_select: requestedIntegrations.map((name) => ({ name })),
              },
              'Last Activity': {
                date: { start: new Date().toISOString() },
              },
            },
          });

          logger.info('✅ Tracked integration request in Notion CRM', {
            tenantId,
            integration,
          });
        }

        return true;
      } catch (error) {
        logger.error('Failed to track integration request in Notion CRM', error, {
          tenantId,
          integration,
        });
        return false;
      }
    }
  );
}

/**
 * Update integration connection status
 */
export async function updateIntegrationStatus(
  tenantId: string,
  integration: string,
  connected: boolean
): Promise<boolean> {
  return LogContext.run(
    { operation: 'notion-crm-update-integration', tenantId, integration, connected },
    async () => {
      if (!isNotionCrmEnabled()) {
        logger.debug('Notion CRM not enabled, skipping integration status update');
        return false;
      }

      const pageId = await findPageIdForTenant(tenantId);
      if (!pageId) {
        logger.warn('Could not find Notion page for tenant', { tenantId });
        return false;
      }

      const client = getNotionClient();
      if (!client) {
        return false;
      }

      try {
        // Get current page to read existing integrations
        const page = await client.pages.retrieve({ page_id: pageId });

        // Extract current integrations
        const currentIntegrations: string[] = [];
        if ('properties' in page) {
          const integrationsProperty = page.properties['Connected Integrations'];
          if (integrationsProperty && integrationsProperty.type === 'multi_select') {
            currentIntegrations.push(...integrationsProperty.multi_select.map((item) => item.name));
          }
        }

        // Update integrations list
        let updatedIntegrations: string[];
        if (connected) {
          // Add integration if not already present
          if (!currentIntegrations.includes(integration)) {
            updatedIntegrations = [...currentIntegrations, integration];
          } else {
            updatedIntegrations = currentIntegrations;
          }
        } else {
          // Remove integration
          updatedIntegrations = currentIntegrations.filter((i) => i !== integration);
        }

        // Check if this is the first integration
        const isFirstIntegration = updatedIntegrations.length === 1 && connected;

        // Update page
        await client.pages.update({
          page_id: pageId,
          properties: {
            'Connected Integrations': {
              multi_select: updatedIntegrations.map((name) => ({ name })),
            },
            'First Integration Connected': {
              checkbox: updatedIntegrations.length > 0,
            },
            'Last Activity': {
              date: { start: new Date().toISOString() },
            },
          },
        });

        logger.info('✅ Updated integration status in Notion CRM', {
          tenantId,
          integration,
          connected,
          isFirstIntegration,
        });

        // Check if onboarding is complete
        await checkAndUpdateOnboardingState(tenantId);

        return true;
      } catch (error) {
        logger.error('Failed to update integration status in Notion CRM', error, {
          tenantId,
          integration,
        });
        return false;
      }
    }
  );
}

/**
 * Check if onboarding is complete and update state accordingly
 * Onboarding is complete when: Slack Bot Configured = true AND at least 1 integration connected
 */
export async function checkAndUpdateOnboardingState(tenantId: string): Promise<boolean> {
  return LogContext.run({ operation: 'notion-crm-check-onboarding', tenantId }, async () => {
    if (!isNotionCrmEnabled()) {
      return false;
    }

    const pageId = await findPageIdForTenant(tenantId);
    if (!pageId) {
      return false;
    }

    const client = getNotionClient();
    if (!client) {
      return false;
    }

    try {
      // Get current page state
      const page = await client.pages.retrieve({ page_id: pageId });

      if (!('properties' in page)) {
        return false;
      }

      // Check Slack Bot Configured
      const slackBotProp = page.properties['Slack Bot Configured'];
      const slackBotConfigured =
        slackBotProp && slackBotProp.type === 'checkbox' && slackBotProp.checkbox;

      // Check Connected Integrations
      const integrationsProp = page.properties['Connected Integrations'];
      const hasIntegrations =
        integrationsProp &&
        integrationsProp.type === 'multi_select' &&
        integrationsProp.multi_select.length > 0;

      // Check current onboarding state
      const stateProp = page.properties['Onboarding State'];
      const currentState = stateProp && stateProp.type === 'select' ? stateProp.select?.name : null;

      // If already onboarded, don't change
      if (currentState === 'onboarded') {
        return true;
      }

      // Check if conditions are met for onboarding completion
      if (slackBotConfigured && hasIntegrations) {
        await client.pages.update({
          page_id: pageId,
          properties: {
            'Onboarding State': {
              select: { name: 'onboarded' },
            },
            'Onboarded At': {
              date: { start: new Date().toISOString() },
            },
            'Last Activity': {
              date: { start: new Date().toISOString() },
            },
          },
        });

        logger.info('✅ Customer onboarded - updated Notion CRM state', {
          tenantId,
        });

        return true;
      }

      return false;
    } catch (error) {
      logger.error('Failed to check/update onboarding state in Notion CRM', error, {
        tenantId,
      });
      return false;
    }
  });
}
