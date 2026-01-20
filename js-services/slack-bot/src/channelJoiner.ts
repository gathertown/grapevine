import { WebClient } from '@slack/web-api';
import type { Channel } from '@slack/web-api/dist/response/ConversationsInfoResponse';
import { getTenantSlackAppManager } from './tenantSlackAppManager';
import { shouldJoinChannel } from './utils/channelUtils';
import { logger, LogContext } from './utils/logger';

/**
 * Get all channels from Slack API with pagination
 */
async function getAllChannels(client: WebClient): Promise<Channel[]> {
  const allChannels: Channel[] = [];
  let cursor: string | undefined;

  do {
    const response = await client.conversations.list({
      types: 'public_channel,private_channel',
      exclude_archived: true,
      limit: 1000,
      cursor,
    });

    if (!response.channels) {
      throw new Error('No channels found or error retrieving channels');
    }

    // Filter out channels without IDs and cast to Channel
    const validChannels = response.channels
      .filter((channel) => channel.id)
      .map((channel) => channel as Channel);
    allChannels.push(...validChannels);
    cursor = response.response_metadata?.next_cursor;

    if (cursor) {
      logger.debug(
        `Fetched batch of ${response.channels.length} channels, getting more with cursor: ${cursor}`,
        {
          batchSize: response.channels.length,
          cursor,
        }
      );
    }
  } while (cursor);

  logger.info(`Found ${allChannels.length} total channels`, { totalChannels: allChannels.length });
  return allChannels;
}

/**
 * Join channels that the bot is not already a member of
 */
async function joinChannels(channelsToJoin: Channel[], client: WebClient): Promise<void> {
  if (channelsToJoin.length === 0) {
    logger.info('Already joined all required channels for QA and additional features');
    return;
  }

  logger.info(`Joining ${channelsToJoin.length} channels...`, {
    channelCount: channelsToJoin.length,
  });

  for (const channel of channelsToJoin) {
    try {
      logger.info(`Joining channel: ${channel.name}`, {
        channelName: channel.name,
        channelId: channel.id,
      });
      await client.conversations.join({ channel: channel.id || '' });
    } catch (error) {
      logger.error(`Failed to join channel ${channel.name}`, error, {
        channelName: channel.name,
        channelId: channel.id,
      });
    }
  }

  logger.info('Channel joining complete');
}

/**
 * Joins all channels that the bot is not already a member of
 * This helps ensure the bot can respond to questions in all channels
 *
 * @param tenantId - Optional tenant ID for multi-tenant mode. If not provided, uses debug client.
 */
export async function joinAllowedChannels(tenantId: string): Promise<void> {
  return LogContext.run({ tenant_id: tenantId }, async () => {
    logger.info(`🔄 Starting to join all available channels for tenant ${tenantId}`);

    // Get appropriate Slack client
    // Multi-tenant mode: get tenant-specific client
    const appManager = getTenantSlackAppManager();
    const tenantSlackApp = await appManager.getTenantSlackApp(tenantId);
    const client = tenantSlackApp.client;

    // Get all channels from Slack
    const allChannels = await getAllChannels(client);

    // Show currently joined channels
    const joinedChannels = allChannels
      .filter((channel: Channel) => channel.is_member)
      .map((channel: Channel) => channel.id);
    logger.info('Currently joined channels', { joinedChannelCount: joinedChannels.length });

    // Count channels by category for logging
    const alreadyMemberCount = allChannels.filter((channel) => channel.is_member).length;
    const privateChannelCount = allChannels.filter((channel) => channel.is_private).length;
    const archivedChannelCount = allChannels.filter((channel) => channel.is_archived).length;
    const slackConnectChannelCount = allChannels.filter((channel) => channel.is_ext_shared).length;

    // Find all channels that need to be joined using our standard criteria
    const channelsToJoin = allChannels.filter(shouldJoinChannel);

    logger.info(`📊 Channel analysis: ${allChannels.length} total channels found`, {
      totalChannels: allChannels.length,
      alreadyMember: alreadyMemberCount,
      privateChannels: privateChannelCount,
      archivedChannels: archivedChannelCount,
      slackConnectChannels: slackConnectChannelCount,
      channelsToJoin: channelsToJoin.length,
    });

    // Join the channels
    await joinChannels(channelsToJoin, client);

    logger.info('✅ Channel joining process completed');
  });
}
