import { Client } from '@notionhq/client';
import { logger } from '../utils/logger.js';

let notionClient: Client | null = null;
let cachedDataSourceId: string | null = null;

/**
 * Get or create Notion client instance
 */
export function getNotionClient(): Client | null {
  // Check if Notion CRM is enabled
  const enabled = process.env.NOTION_CRM_ENABLED !== 'false'; // Default to true
  if (!enabled) {
    return null;
  }

  // Return existing client if available
  if (notionClient) {
    return notionClient;
  }

  // Check for required environment variables
  const token = process.env.NOTION_CRM_TOKEN;
  if (!token) {
    logger.warn('NOTION_CRM_TOKEN not configured, Notion CRM disabled');
    return null;
  }

  // Create new client with the latest API version
  try {
    notionClient = new Client({
      auth: token,
      notionVersion: '2025-09-03',
    });
    logger.info('Notion CRM client initialized successfully');
    return notionClient;
  } catch (error) {
    logger.error('Failed to initialize Notion CRM client', error);
    return null;
  }
}

/**
 * Get Notion CRM database ID from environment
 */
export function getNotionDatabaseId(): string | null {
  const databaseId = process.env.NOTION_CRM_DATABASE_ID;
  if (!databaseId) {
    logger.warn('NOTION_CRM_DATABASE_ID not configured');
    return null;
  }
  return databaseId;
}

/**
 * Get the data source ID for the CRM database
 * In the new Notion API (2025-09-03), databases can have multiple data sources
 */
export async function getNotionDataSourceId(): Promise<string | null> {
  // Return cached value if available
  if (cachedDataSourceId) {
    return cachedDataSourceId;
  }

  const client = getNotionClient();
  const databaseId = getNotionDatabaseId();

  if (!client || !databaseId) {
    return null;
  }

  try {
    // Retrieve the database to get its data sources
    const database = await client.databases.retrieve({ database_id: databaseId });

    // In the 2025-09-03 API, databases have a data_sources array
    if ('data_sources' in database && Array.isArray(database.data_sources)) {
      const dataSources = database.data_sources as Array<{ id: string }>;
      if (dataSources.length > 0) {
        cachedDataSourceId = dataSources[0]?.id || null;
        logger.info('Discovered Notion CRM data source ID', {
          databaseId,
          dataSourceId: cachedDataSourceId,
        });
        return cachedDataSourceId;
      }
    }

    logger.error('No data sources found in database response', { databaseId });
    return null;
  } catch (error) {
    logger.error('Failed to discover Notion CRM data source ID', error, { databaseId });
    return null;
  }
}

/**
 * Check if Notion CRM is enabled and configured
 */
export function isNotionCrmEnabled(): boolean {
  return getNotionClient() !== null && getNotionDatabaseId() !== null;
}
