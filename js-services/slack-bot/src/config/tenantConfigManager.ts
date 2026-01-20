/**
 * Tenant Configuration Manager for Slack Bot
 *
 * Provides Slack-specific configuration retrieval from database
 * Uses shared TenantConfigManager from backend-common
 */

import { TenantConfigManager } from '@corporate-context/backend-common';
import { tenantDbConnectionManager } from './tenantDbConnectionManager';
import { logger } from '../utils/logger';

export type ConfigKey =
  | 'SLACK_BOT_QA_ALL_CHANNELS'
  | 'SLACK_BOT_QA_ALLOWED_CHANNELS'
  | 'SLACK_BOT_QA_DISALLOWED_CHANNELS'
  | 'SLACK_BOT_QA_CONFIDENCE_THRESHOLD'
  | 'SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS'
  | 'SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS'
  | 'SLACK_BOT_MIRROR_QUESTIONS_CHANNEL_NAME'
  | 'SLACK_INSTALLER_USER_ID'
  | 'SLACK_BOT_NAME'
  | 'SLACK_INSTALLER_DM_SENT'
  | 'LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS'
  | 'TRIAGE_BOT_PROACTIVE_MODE';

export type ConfigValue = string | boolean | null;

interface LinearTeam {
  id: string;
  name: string;
}

interface LinearTeamMapping {
  linearTeam: LinearTeam;
  channels: string[];
}

// Create base tenant config manager instance
const baseTenantConfigManager = new TenantConfigManager({
  getDbPool: (tenantId: string) => tenantDbConnectionManager.get(tenantId),
});

/**
 * Slack-specific tenant configuration manager
 * Wraps the base TenantConfigManager with Slack-specific helper methods
 */
class SlackTenantConfigManager {
  private baseManager: TenantConfigManager;

  constructor(baseManager: TenantConfigManager) {
    this.baseManager = baseManager;
  }

  /**
   * Get a configuration value from the tenant-specific database
   */
  async getConfigValue(key: ConfigKey, tenantId: string): Promise<ConfigValue> {
    return this.baseManager.getConfigValue(key, tenantId);
  }

  /**
   * Set a configuration value in the tenant-specific database
   */
  async setConfigValue(key: ConfigKey, value: ConfigValue, tenantId: string): Promise<boolean> {
    return this.baseManager.setConfigValue(key, value, tenantId);
  }

  /**
   * Get QA allowed channels for a tenant
   */
  async getQaAllowedChannels(tenantId: string): Promise<string[]> {
    const value = await this.getConfigValue('SLACK_BOT_QA_ALLOWED_CHANNELS', tenantId);
    if (typeof value === 'string' && value.trim()) {
      return value.split(',').map((c) => c.trim());
    }
    return [];
  }

  /**
   * Get QA disallowed channels for a tenant
   */
  async getQaDisallowedChannels(tenantId: string): Promise<string[]> {
    const value = await this.getConfigValue('SLACK_BOT_QA_DISALLOWED_CHANNELS', tenantId);
    if (typeof value === 'string' && value.trim()) {
      return value.split(',').map((c) => c.trim());
    }
    return [];
  }

  /**
   * Get QA all channels setting for a tenant
   */
  async getQaAllChannels(tenantId: string): Promise<boolean> {
    const value = await this.getConfigValue('SLACK_BOT_QA_ALL_CHANNELS', tenantId);
    if (typeof value === 'string') {
      return value.toLowerCase() === 'true';
    }
    if (typeof value === 'boolean') {
      return value;
    }
    return false;
  }

  /**
   * Get QA skip channels with external guests setting for a tenant
   */
  async getQaSkipChannelsWithExternalGuests(tenantId: string): Promise<boolean> {
    const value = await this.getConfigValue(
      'SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS',
      tenantId
    );
    if (typeof value === 'string') {
      return value.toLowerCase() === 'true';
    }
    if (typeof value === 'boolean') {
      return value;
    }
    return false;
  }

  /**
   * Get QA skip mentions by non-members setting for a tenant
   * When true, bot will not respond to @mentions from users who are
   * not full members (guests, restricted users, or external workspace users)
   */
  async getQaSkipMentionsByNonMembers(tenantId: string): Promise<boolean> {
    const value = await this.getConfigValue('SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS', tenantId);
    if (typeof value === 'string') {
      return value.toLowerCase() === 'true';
    }
    if (typeof value === 'boolean') {
      return value;
    }
    return true; // Default: skip mentions from non-members (secure)
  }

  /**
   * Get mirror questions channel for a tenant
   */
  async getMirrorQuestionsChannel(tenantId: string): Promise<string | null> {
    const value = await this.getConfigValue('SLACK_BOT_MIRROR_QUESTIONS_CHANNEL_NAME', tenantId);
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    return null;
  }

  /**
   * Get Slack installer user ID for a tenant
   */
  async getSlackInstallerUserId(tenantId: string): Promise<string | null> {
    const value = await this.getConfigValue('SLACK_INSTALLER_USER_ID', tenantId);
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    return null;
  }

  /**
   * Get Slack bot name for a tenant
   */
  async getSlackBotName(tenantId: string): Promise<string | null> {
    const value = await this.getConfigValue('SLACK_BOT_NAME', tenantId);
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    return null;
  }

  /**
   * Get QA confidence threshold for a tenant
   * Returns the configured threshold or a default if not set/invalid
   */
  async getQaConfidenceThreshold(tenantId: string): Promise<number> {
    const value = await this.getConfigValue('SLACK_BOT_QA_CONFIDENCE_THRESHOLD', tenantId);

    if (typeof value === 'string' && value.trim()) {
      const numValue = parseFloat(value.trim());
      if (!isNaN(numValue) && numValue >= 0 && numValue <= 100) {
        return numValue;
      }
    }

    // Default to 80% if not configured or invalid
    return 80;
  }

  /**
   * Get Linear team to Slack channel mappings from tenant config
   * @returns Array of Linear team mappings, or empty array if not configured
   */
  async getLinearTeamMappings(tenantId: string): Promise<LinearTeamMapping[]> {
    try {
      const mappingsJson = await this.getConfigValue(
        'LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS',
        tenantId
      );

      if (!mappingsJson || typeof mappingsJson !== 'string') {
        logger.debug('[LinearTeamMappings] No mappings configured for tenant', { tenantId });
        return [];
      }

      const mappings: LinearTeamMapping[] = JSON.parse(mappingsJson);

      logger.debug('[LinearTeamMappings] Retrieved Linear team mappings from config', {
        tenantId,
        mappingCount: mappings.length,
      });

      return mappings;
    } catch (error) {
      logger.error(
        '[LinearTeamMappings] Error retrieving or parsing Linear team mappings',
        error instanceof Error ? error : new Error(String(error)),
        { tenantId }
      );
      return [];
    }
  }

  /**
   * Get triage bot proactive mode setting for a tenant
   * When true, triage bot automatically creates/updates Linear tickets
   * When false, triage bot shows analysis with buttons and waits for user action
   * @returns true (proactive) or false (non-proactive), defaults to true
   */
  async getTriageProactiveMode(tenantId: string): Promise<boolean> {
    const value = await this.getConfigValue('TRIAGE_BOT_PROACTIVE_MODE', tenantId);
    if (typeof value === 'string') {
      return value.toLowerCase() === 'true';
    }
    if (typeof value === 'boolean') {
      return value;
    }
    return true; // Default: proactive mode enabled (current behavior)
  }

  /**
   * Set triage bot proactive mode setting for a tenant
   * @param tenantId - The tenant ID
   * @param enabled - true for proactive mode, false for non-proactive mode
   * @returns true if set successfully, false otherwise
   */
  async setTriageProactiveMode(tenantId: string, enabled: boolean): Promise<boolean> {
    return await this.setConfigValue('TRIAGE_BOT_PROACTIVE_MODE', String(enabled), tenantId);
  }
}

// Export singleton instance
export const tenantConfigManager = new SlackTenantConfigManager(baseTenantConfigManager);
