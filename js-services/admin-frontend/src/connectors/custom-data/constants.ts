/**
 * Constants for Custom Data connector
 */

import { getConfig } from '../../lib/config';

// Custom data ingest endpoint path template
const CUSTOM_DATA_PATH = '/custom-documents';

/**
 * Get the ingest base URL for a tenant
 * Uses the same pattern as webhook URLs: {tenant_id}.ingest.{base_domain}
 *
 * @param tenantId - The tenant identifier
 * @returns The base URL for the ingest API
 */
export const getIngestBaseUrl = (tenantId: string): string => {
  const config = getConfig();
  const baseDomain = config.BASE_DOMAIN;

  if (!baseDomain || baseDomain === 'localhost') {
    // Local development - use gatekeeper directly
    return `http://localhost:8001/${tenantId}`;
  }

  // Same pattern as webhooks: {tenant_id}.ingest.{base_domain}
  return `https://${tenantId}.ingest.${baseDomain}`;
};

/**
 * Build the full ingest endpoint URL for a data type (POST - create)
 */
export const buildIngestEndpoint = (tenantId: string, slug: string): string => {
  const baseUrl = getIngestBaseUrl(tenantId);
  return `POST ${baseUrl}${CUSTOM_DATA_PATH}/${slug}`;
};

/**
 * Get all available API endpoints for a custom data type
 */
export interface CustomDataEndpoint {
  method: string;
  path: string;
  description: string;
}

export const getCustomDataEndpoints = (tenantId: string, slug: string): CustomDataEndpoint[] => {
  const baseUrl = getIngestBaseUrl(tenantId);
  const basePath = `${baseUrl}${CUSTOM_DATA_PATH}/${slug}`;

  return [
    {
      method: 'POST',
      path: basePath,
      description: 'Create a new document (or batch with {"documents": [...]})',
    },
    {
      method: 'GET',
      path: `${basePath}/{item_id}`,
      description: 'Retrieve a document by ID',
    },
    {
      method: 'PUT',
      path: `${basePath}/{item_id}`,
      description: 'Update an existing document',
    },
    {
      method: 'DELETE',
      path: `${basePath}/{item_id}`,
      description: 'Delete a document',
    },
  ];
};

/**
 * Build a curl example for ingesting data
 */
export const buildCurlExample = (
  tenantId: string,
  slug: string,
  payload: Record<string, unknown>
): string => {
  const baseUrl = getIngestBaseUrl(tenantId);
  return `curl -X POST \\
  ${baseUrl}${CUSTOM_DATA_PATH}/${slug} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '${JSON.stringify(payload, null, 2)}'`;
};

// Example field values for API documentation
export const EXAMPLE_FIELD_VALUES = {
  number: 42,
  date: '2024-01-15',
  text: (fieldName: string) => `example-${fieldName}`,
} as const;
