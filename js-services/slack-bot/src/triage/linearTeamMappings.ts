import { logger } from '../utils/logger';
import { tenantConfigManager } from '../config/tenantConfigManager';

/**
 * Get the Linear team ID for a given Slack channel
 * @param channelId - The Slack channel ID
 * @param tenantId - The tenant ID
 * @returns The Linear team ID, or null if no mapping exists
 */
export async function getLinearTeamIdForTriageChannel(
  channelId: string,
  tenantId: string
): Promise<string | null> {
  try {
    const mappings = await tenantConfigManager.getLinearTeamMappings(tenantId);

    // Find the Linear team that has this channel mapped
    for (const mapping of mappings) {
      if (mapping.channels.includes(channelId)) {
        logger.debug('[LinearTeamMappings] Found Linear team for channel', {
          channelId,
          linearTeamId: mapping.linearTeam.id,
          linearTeamName: mapping.linearTeam.name,
          tenantId,
        });
        return mapping.linearTeam.id;
      }
    }

    logger.debug('[LinearTeamMappings] No Linear team found for channel');

    return null;
  } catch (error) {
    logger.error(
      'Error getting Linear team ID for channel',
      error instanceof Error ? error : new Error(String(error))
    );
    return null;
  }
}
