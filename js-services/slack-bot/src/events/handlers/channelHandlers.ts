import { BasicEventArgs, ChannelCreatedEvent } from '../../types';
import { shouldJoinChannel } from '../../utils/channelUtils';
import { isBotMentioned } from '../../common';
import { processDMThreadOrChannelThreadMention, processChannelMention } from '../../question';
import { GenericMessageEvent } from '@slack/bolt';
import type { Channel } from '@slack/web-api/dist/response/ConversationsInfoResponse';
import { logger } from '../../utils/logger';

interface MemberJoinedChannelEvent {
  type: 'member_joined_channel';
  user: string;
  channel: string;
}

interface MemberLeftChannelEvent {
  type: 'member_left_channel';
  user: string;
  channel: string;
}

export async function onChannelCreated(args: BasicEventArgs<ChannelCreatedEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  logger.info('New channel created', {
    tenantId: tenantSlackApp.tenantId,
    channelName: event.channel.name,
    channelId: event.channel.id,
    operation: 'channel-created',
  });

  // Get full channel information to apply filtering logic
  const channelInfo = await tenantSlackApp.client.conversations.info({
    channel: event.channel.id,
  });

  if (!channelInfo.channel) {
    throw new Error(`Failed to get channel info for ${event.channel.name}`);
  }

  const channel = channelInfo.channel as Channel;

  // Apply same filtering logic as bulk channel joiner
  if (!shouldJoinChannel(channel)) {
    logger.debug('Skipping channel - does not meet join criteria', {
      tenantId: tenantSlackApp.tenantId,
      channelName: event.channel.name,
      channelId: event.channel.id,
      isPrivate: channel.is_private,
      isArchived: channel.is_archived,
      isMember: channel.is_member,
      operation: 'channel-skip',
    });
    return;
  }

  await tenantSlackApp.client.conversations.join({ channel: event.channel.id });
  logger.info('Successfully joined new channel', {
    tenantId: tenantSlackApp.tenantId,
    channelName: event.channel.name,
    channelId: event.channel.id,
    operation: 'channel-joined',
  });
}

export async function onChannelJoined(
  args: BasicEventArgs<MemberJoinedChannelEvent>
): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    // Only handle when the bot itself is invited to a channel
    if (event.user === tenantSlackApp.botId) {
      logger.info('Bot invited to channel', {
        tenantId: tenantSlackApp.tenantId,
        channelId: event.channel,
        operation: 'bot-invited',
      });
      // The bot is already in the channel when this event fires, so no need to join
      logger.info('Bot confirmed in channel after invitation', {
        tenantId: tenantSlackApp.tenantId,
        channelId: event.channel,
        operation: 'bot-in-channel',
      });

      // Check for recent mentions of the bot in the channel
      logger.debug('Checking for recent mentions in newly joined channel', {
        tenantId: tenantSlackApp.tenantId,
        channelId: event.channel,
        operation: 'mention-check',
      });

      try {
        // Get recent messages from the channel (last hour)
        const oneHourAgo = Math.floor((Date.now() - 60 * 60 * 1000) / 1000);

        const response = await tenantSlackApp.client.conversations.history({
          channel: event.channel,
          oldest: oneHourAgo.toString(),
          limit: 50, // Check last 50 messages or last hour, whichever comes first
        });

        if (response.messages && response.messages.length > 0) {
          logger.debug('Found recent messages in channel', {
            tenantId: tenantSlackApp.tenantId,
            channelId: event.channel,
            messageCount: response.messages.length,
            operation: 'recent-messages',
          });

          // Filter messages that mention the bot (exclude bot messages)
          interface SlackMessage {
            text?: string;
            bot_id?: string;
            user?: string;
            ts?: string;
            thread_ts?: string;
          }
          const botMentions = response.messages.filter(
            (msg: SlackMessage) =>
              msg.text &&
              isBotMentioned(msg.text, tenantSlackApp.botId) &&
              !msg.bot_id &&
              msg.user !== tenantSlackApp.botId
          );

          if (botMentions.length > 0) {
            logger.info('Found bot mentions in newly joined channel', {
              tenantId: tenantSlackApp.tenantId,
              channelId: event.channel,
              mentionCount: botMentions.length,
              operation: 'bot-mentions-found',
            });

            // Process each mention as a question
            for (const mention of botMentions) {
              logger.debug('Processing bot mention from recent history', {
                tenantId: tenantSlackApp.tenantId,
                channelId: event.channel,
                userId: mention.user,
                messageTs: mention.ts,
                operation: 'mention-processing',
              });

              // Skip mentions from bot users
              if (mention.user) {
                try {
                  const userInfo = await tenantSlackApp.client.users.info({
                    user: mention.user,
                  });
                  if (userInfo.user?.is_bot) {
                    logger.debug('Skipping mention from bot user', {
                      tenantId: tenantSlackApp.tenantId,
                      channelId: event.channel,
                      userId: mention.user,
                      operation: 'mention-skip-bot',
                    });
                    continue;
                  }
                } catch (error) {
                  logger.error(
                    'Error checking user info for mention processing',
                    error instanceof Error ? error : new Error(String(error)),
                    {
                      tenantId: tenantSlackApp.tenantId,
                      channelId: event.channel,
                      userId: mention.user,
                      operation: 'user-info-error',
                    }
                  );
                  // Continue processing if we can't check user info
                }
              }

              // Create a proper message event object
              // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
              const messageEvent = {
                ...mention,
                type: 'message' as const,
                channel: event.channel,
                channel_type: 'channel' as const,
                event_ts: mention.ts || '',
                subtype: undefined,
                user: mention.user || '',
              } as GenericMessageEvent;

              // Process the mention based on whether it's in a thread or not
              if (mention.thread_ts) {
                await processDMThreadOrChannelThreadMention(messageEvent, tenantSlackApp);
              } else {
                await processChannelMention(messageEvent, tenantSlackApp);
              }
            }
          } else {
            logger.debug('No recent bot mentions found in newly joined channel', {
              tenantId: tenantSlackApp.tenantId,
              channelId: event.channel,
              operation: 'no-mentions',
            });
          }
        }
      } catch (error) {
        logger.error(
          'Error checking for recent mentions in newly joined channel',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenantId: tenantSlackApp.tenantId,
            channelId: event.channel,
            operation: 'mention-check-error',
          }
        );
      }
    }
  } catch (error) {
    logger.error(
      'Error handling channel invite event',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        channelId: event.channel,
        operation: 'channel-invite-error',
      }
    );
  }
}

export async function onChannelLeft(args: BasicEventArgs<MemberLeftChannelEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    logger.debug('User left channel', {
      tenantId: tenantSlackApp.tenantId,
      userId: event.user,
      channelId: event.channel,
      operation: 'user-left-channel',
    });

    // Get bot info to check if it's the bot that left
    const authResponse = await tenantSlackApp.client.auth.test();
    const botUserId = authResponse.user_id;

    if (event.user === botUserId) {
      logger.info('Bot removed from channel', {
        tenantId: tenantSlackApp.tenantId,
        channelId: event.channel,
        operation: 'bot-removed',
      });
      // Bot was removed from channel - cleanup if needed
    }
  } catch (error) {
    logger.error(
      'Error handling member left channel event',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        userId: event.user,
        channelId: event.channel,
        operation: 'member-left-error',
      }
    );
    throw error;
  }
}
