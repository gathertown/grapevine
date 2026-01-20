import { logger } from '../../utils/logger';

// Constants
const SECONDS_PER_DAY = 86400;

// Column indices for DESCRIBE SECURITY INTEGRATION result
const DESCRIBE_COL = {
  PROPERTY: 0,
  PROPERTY_TYPE: 1,
  PROPERTY_VALUE: 2,
  PROPERTY_DEFAULT: 3,
} as const;

const DESCRIBE_REQUIRED_COLUMNS = 3;

/**
 * Safely quote a Snowflake identifier to prevent SQL injection.
 * Wraps in double quotes and escapes any embedded double quotes.
 */
function quoteIdentifier(identifier: string): string {
  // Escape any double quotes by doubling them, then wrap in double quotes
  return `"${identifier.replace(/"/g, '""')}"`;
}

/**
 * Query Snowflake security integration properties to get OAuth configuration.
 *
 * @param accountIdentifier Snowflake account identifier
 * @param integrationName Name of the security integration
 * @param accessToken OAuth access token with permission to describe integrations
 * @returns Object with integration properties
 */
export async function describeSecurityIntegration(
  accountIdentifier: string,
  integrationName: string,
  accessToken: string
): Promise<Record<string, string> | null> {
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
        statement: `DESCRIBE SECURITY INTEGRATION ${quoteIdentifier(integrationName)}`,
        timeout: 30,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('Failed to describe security integration', {
        status: response.status,
        error: errorText,
        integration_name: integrationName,
      });
      return null;
    }

    const result = await response.json();

    // Parse the result
    // Format: {data: [[property, value, default, type], ...]}
    if (!result.data || !Array.isArray(result.data)) {
      logger.error('Unexpected response format from DESCRIBE INTEGRATION', {
        result,
      });
      return null;
    }

    // Convert array of arrays to object
    // Format: [[property, property_type, property_value, property_default], ...]
    const properties: Record<string, string> = {};
    for (const row of result.data) {
      if (row.length >= DESCRIBE_REQUIRED_COLUMNS) {
        const property = row[DESCRIBE_COL.PROPERTY] as string;
        const value = row[DESCRIBE_COL.PROPERTY_VALUE] as string;
        properties[property] = value;
      }
    }

    return properties;
  } catch (error) {
    logger.error('Error querying security integration', {
      error,
      integration_name: integrationName,
    });
    return null;
  }
}

/**
 * Get the OAUTH_REFRESH_TOKEN_VALIDITY from a security integration.
 *
 * @param accountIdentifier Snowflake account identifier
 * @param integrationName Name of the security integration
 * @param accessToken OAuth access token
 * @returns Refresh token validity in seconds, or null if not found
 */
export async function getOAuthRefreshTokenValidity(
  accountIdentifier: string,
  integrationName: string,
  accessToken: string
): Promise<number | null> {
  const properties = await describeSecurityIntegration(
    accountIdentifier,
    integrationName,
    accessToken
  );

  if (!properties) {
    return null;
  }

  const validity = properties['OAUTH_REFRESH_TOKEN_VALIDITY'];
  if (!validity) {
    logger.warn('OAUTH_REFRESH_TOKEN_VALIDITY not found in security integration', {
      integration_name: integrationName,
      available_properties: Object.keys(properties),
    });
    return null;
  }

  const validitySeconds = parseInt(validity, 10);
  if (isNaN(validitySeconds)) {
    logger.error('Invalid OAUTH_REFRESH_TOKEN_VALIDITY value', {
      value: validity,
      integration_name: integrationName,
    });
    return null;
  }

  logger.info('Retrieved OAUTH_REFRESH_TOKEN_VALIDITY from Snowflake', {
    integration_name: integrationName,
    validity_seconds: validitySeconds,
    validity_days: Math.floor(validitySeconds / SECONDS_PER_DAY),
  });

  return validitySeconds;
}
