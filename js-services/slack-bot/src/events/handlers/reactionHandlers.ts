import { BasicEventArgs, ReactionAddedEvent, ReactionRemovedEvent } from '../../types';
import { storeReaction, removeReaction } from '../../common';
import { logger } from '../../utils/logger';
import { getAnalyticsTracker } from '../../services/analyticsTracker';
import { tenantDbConnectionManager } from '../../config/tenantDbConnectionManager';

// Valid feedback reactions that we track (positive and negative)

export async function onReactionAdded(args: BasicEventArgs<ReactionAddedEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    logger.info('Reaction added event received', {
      tenantId: tenantSlackApp.tenantId,
      reaction: event.reaction,
      userId: event.user,
      messageId: event.item.ts,
      channelId: event.item.channel,
      operation: 'reaction-added',
    });

    const pool = await tenantDbConnectionManager.get(tenantSlackApp.tenantId);
    if (!pool) {
      logger.error('Unable to get database pool for tenant', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'reaction-added-db-error',
      });
      return;
    }

    const result = await pool.query(
      'SELECT bot_response_message_id FROM slack_messages WHERE bot_response_message_id = $1',
      [event.item.ts]
    );

    const isBotMessage = result.rows.length > 0;

    if (!isBotMessage) {
      logger.debug('Skipping reaction storage - not a bot message', {
        tenantId: tenantSlackApp.tenantId,
        messageId: event.item.ts,
        channelId: event.item.channel,
        operation: 'reaction-skip',
      });
      return;
    }

    // Skip reactions from the bot itself (bot shouldn't react to its own messages)
    if (event.user === tenantSlackApp.botId) {
      logger.debug('Skipping reaction storage - bot reacting to itself', {
        tenantId: tenantSlackApp.tenantId,
        reactingUser: event.user,
        botId: tenantSlackApp.botId,
        messageId: event.item.ts,
        channelId: event.item.channel,
        operation: 'bot-self-reaction-skip',
      });
      return;
    }

    // Store the reaction
    await storeReaction(
      tenantSlackApp.tenantId,
      event.item.ts,
      event.item.channel,
      event.user,
      event.reaction
    );

    logger.info('Successfully stored reaction', {
      tenantId: tenantSlackApp.tenantId,
      reaction: event.reaction,
      userId: event.user,
      messageId: event.item.ts,
      channelId: event.item.channel,
      operation: 'reaction-stored',
    });

    // Track user reaction event
    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(event.item.channel);
    await analyticsTracker.trackUserReaction(
      tenantSlackApp.tenantId,
      event.reaction,
      event.item.ts,
      event.item.channel,
      channelName,
      event.user
    );
  } catch (error) {
    logger.error(
      'Error handling reaction_added event',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        reaction: event.reaction,
        userId: event.user,
        messageId: event.item.ts,
        channelId: event.item.channel,
        operation: 'reaction-added-error',
      }
    );
  }
}

export async function onReactionRemoved(args: BasicEventArgs<ReactionRemovedEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    // Remove the reaction from database
    await removeReaction(tenantSlackApp.tenantId, event.item.ts, event.user, event.reaction);

    logger.info('Successfully removed reaction', {
      tenantId: tenantSlackApp.tenantId,
      reaction: event.reaction,
      userId: event.user,
      messageId: event.item.ts,
      channelId: event.item.channel,
      operation: 'reaction-removed',
    });
  } catch (error) {
    logger.error(
      'Error handling reaction_removed event',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        reaction: event.reaction,
        userId: event.user,
        messageId: event.item.ts,
        channelId: event.item.channel,
        operation: 'reaction-removed-error',
      }
    );
  }
}
