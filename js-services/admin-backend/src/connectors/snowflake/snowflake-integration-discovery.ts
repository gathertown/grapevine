import { logger } from '../../utils/logger';
import { describeSecurityIntegration } from './snowflake-integration-query';

// Column indices for SHOW INTEGRATIONS result
const INTEGRATION_COL = {
  NAME: 0,
  TYPE: 1,
  CATEGORY: 2,
  ENABLED: 3,
  COMMENT: 4,
  CREATED_ON: 5,
} as const;

const REQUIRED_COLUMNS = 6;

// Integration filter values
const INTEGRATION_CATEGORY_SECURITY = 'SECURITY';
const INTEGRATION_TYPE_OAUTH = 'OAUTH';
const INTEGRATION_ENABLED_TRUE = 'true';

interface SnowflakeIntegration {
  name: string;
  type: string;
  category: string;
  enabled: string;
  comment: string | null;
  created_on: string;
}

/**
 * Get list of all OAuth security integrations in the Snowflake account.
 *
 * @param accountIdentifier Snowflake account identifier
 * @param accessToken OAuth access token with permission to show integrations
 * @returns Array of integration names
 */
export async function listOAuthIntegrations(
  accountIdentifier: string,
  accessToken: string
): Promise<string[]> {
  try {
    const apiUrl = `https://${accountIdentifier}.snowflakecomputing.com/api/v2/statements`;

    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        'X-Snowflake-Authorization-Token-Type': 'OAUTH',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        statement: `SHOW INTEGRATIONS`,
        timeout: 30,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to list integrations', {
        status: response.status,
        error: errorText,
      });
      return [];
    }

    const result = await response.json();

    // Parse the result
    // Format: {data: [[name, type, category, enabled, ...], ...]}
    if (!result.data || !Array.isArray(result.data)) {
      logger.error('Unexpected response format from SHOW INTEGRATIONS', {
        result,
      });
      return [];
    }

    // Filter for OAuth integrations
    const oauthIntegrations: string[] = [];
    for (const row of result.data) {
      if (row.length >= REQUIRED_COLUMNS) {
        const integration: SnowflakeIntegration = {
          name: row[INTEGRATION_COL.NAME] as string,
          type: row[INTEGRATION_COL.TYPE] as string,
          category: row[INTEGRATION_COL.CATEGORY] as string,
          enabled: row[INTEGRATION_COL.ENABLED] as string,
          comment: row[INTEGRATION_COL.COMMENT] as string | null,
          created_on: row[INTEGRATION_COL.CREATED_ON] as string,
        };

        // Check if this is an OAuth security integration
        if (
          integration.category === INTEGRATION_CATEGORY_SECURITY &&
          integration.type.includes(INTEGRATION_TYPE_OAUTH) &&
          integration.enabled === INTEGRATION_ENABLED_TRUE
        ) {
          oauthIntegrations.push(integration.name);
        }
      }
    }

    logger.info('Found OAuth integrations', {
      count: oauthIntegrations.length,
      integrations: oauthIntegrations,
    });

    return oauthIntegrations;
  } catch (error) {
    logger.error('Error listing integrations', { error });
    return [];
  }
}

/**
 * Find the OAuth security integration that matches the given client ID.
 *
 * @param accountIdentifier Snowflake account identifier
 * @param accessToken OAuth access token
 * @param clientId The OAuth client ID to search for
 * @returns The integration name if found, null otherwise
 */
export async function findIntegrationByClientId(
  accountIdentifier: string,
  accessToken: string,
  clientId: string
): Promise<string | null> {
  try {
    // Get all OAuth integrations
    const integrations = await listOAuthIntegrations(accountIdentifier, accessToken);

    if (integrations.length === 0) {
      logger.warn('No OAuth integrations found in Snowflake account');
      return null;
    }

    // Check each integration to find matching client ID
    for (const integrationName of integrations) {
      const properties = await describeSecurityIntegration(
        accountIdentifier,
        integrationName,
        accessToken
      );

      if (!properties) {
        continue;
      }

      const integrationClientId = properties['OAUTH_CLIENT_ID'];
      if (integrationClientId === clientId) {
        logger.info('Found matching integration for client ID', {
          integration_name: integrationName,
          client_id_prefix: `${clientId.substring(0, 8)}...`,
        });
        return integrationName;
      }
    }

    logger.warn('No integration found matching client ID', {
      client_id_prefix: `${clientId.substring(0, 8)}...`,
      checked_integrations: integrations.length,
    });

    return null;
  } catch (error) {
    logger.error('Error finding integration by client ID', { error });
    return null;
  }
}
