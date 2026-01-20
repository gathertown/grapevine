/**
 * Marketing HubSpot Client
 *
 * This is Grapevine's internal HubSpot client for tracking customer onboarding
 * and marketing automation. This is SEPARATE from the customer-facing HubSpot
 * integration that allows customers to connect their own HubSpot data to Grapevine.
 *
 * Environment variables:
 * - MARKETING_HUBSPOT_ACCESS_TOKEN: Access token for Grapevine's HubSpot account
 * - MARKETING_HUBSPOT_ENABLED: Feature flag to enable/disable tracking
 */

import { Client } from '@hubspot/api-client';
import { logger } from './utils/logger.js';

let marketingHubSpotClient: Client | null = null;

interface MarketingHubSpotConfig {
  accessToken: string;
  enabled: boolean;
}

function getMarketingHubSpotConfig(): MarketingHubSpotConfig | null {
  const accessToken = process.env.MARKETING_HUBSPOT_ACCESS_TOKEN;
  const enabled = process.env.MARKETING_HUBSPOT_ENABLED === 'true';

  if (!enabled) {
    logger.debug('Marketing HubSpot tracking is disabled');
    return null;
  }

  if (!accessToken) {
    logger.warn(
      'Marketing HubSpot tracking is enabled but MARKETING_HUBSPOT_ACCESS_TOKEN is not configured'
    );
    return null;
  }

  return { accessToken, enabled };
}

/**
 * Get or create the marketing HubSpot client instance
 * Returns null if HubSpot tracking is not configured or disabled
 */
export function getMarketingHubSpotClient(): Client | null {
  if (marketingHubSpotClient) {
    return marketingHubSpotClient;
  }

  const config = getMarketingHubSpotConfig();
  if (!config) {
    return null;
  }

  try {
    marketingHubSpotClient = new Client({ accessToken: config.accessToken });
    logger.info('Marketing HubSpot client initialized successfully');
    return marketingHubSpotClient;
  } catch (error) {
    logger.error('Failed to initialize marketing HubSpot client', error);
    return null;
  }
}

/**
 * Check if marketing HubSpot tracking is enabled and configured
 */
export function isMarketingHubSpotEnabled(): boolean {
  const config = getMarketingHubSpotConfig();
  return config !== null;
}

/**
 * Reset the client instance (useful for testing or credential updates)
 */
export function resetMarketingHubSpotClient(): void {
  marketingHubSpotClient = null;
}
