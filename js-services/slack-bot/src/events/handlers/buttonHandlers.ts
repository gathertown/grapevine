import { BlockAction, ButtonAction } from '@slack/bolt';
import { BasicEventArgs } from '../../types';
import { getSlackMessageStorage } from '../../services/slackMessageStorage';
import { logger } from '../../utils/logger';
import { getAnalyticsTracker } from '../../services/analyticsTracker';
import { tenantDbConnectionManager } from '../../config/tenantDbConnectionManager';

export interface BlockActionEvent {
  type: 'block_actions';
  user: {
    id: string;
    username?: string;
    name?: string;
  };
  actions: BlockAction[];
  channel?: {
    id: string;
    name?: string;
  };
  message?: {
    ts: string;
    thread_ts?: string;
  };
  container: {
    type: string;
    message_ts: string;
    channel_id: string;
    is_ephemeral?: boolean;
  };
}

/**
 * Handle feedback button clicks from Slack Block Kit buttons
 * Processes positive/negative feedback and stores in database
 */
export async function onFeedbackButtonClick(args: BasicEventArgs<BlockActionEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    logger.info('Feedback button click received', {
      tenantId: tenantSlackApp.tenantId,
      userId: event.user.id,
      messageTs: event.container.message_ts,
      channelId: event.container.channel_id,
      actionCount: event.actions.length,
      operation: 'feedback-button-click',
    });

    // Extract the button action
    const action = event.actions[0];
    if (!action) {
      logger.warn('No action in feedback button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    // Type guard: check if it's a button action by checking for button-specific properties
    if (!('action_id' in action) || !('value' in action)) {
      logger.warn('Invalid action type in feedback button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    // Now we know action has the properties we need
    const buttonAction = action as unknown as ButtonAction;

    // Validate action_id is a feedback button
    if (!['feedback_positive', 'feedback_negative'].includes(buttonAction.action_id)) {
      logger.debug('Ignoring non-feedback button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'non-feedback-action',
      });
      return;
    }

    const messageTs = event.container.message_ts;
    const channelId = event.container.channel_id;
    const userId = event.user.id;
    const feedbackType = buttonAction.value as 'positive' | 'negative';

    // Verify it's a bot message before storing feedback
    const pool = await tenantDbConnectionManager.get(tenantSlackApp.tenantId);
    if (!pool) {
      logger.error('Unable to get database pool for tenant', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'feedback-button-db-error',
      });
      return;
    }

    const result = await pool.query(
      'SELECT bot_response_message_id FROM slack_messages WHERE bot_response_message_id = $1',
      [messageTs]
    );

    const isBotMessage = result.rows.length > 0;

    if (!isBotMessage) {
      logger.warn('Skipping feedback storage - not a bot message', {
        tenantId: tenantSlackApp.tenantId,
        messageId: messageTs,
        channelId,
        operation: 'feedback-skip',
      });
      return;
    }

    // Skip feedback from the bot itself (shouldn't happen, but be safe)
    if (userId === tenantSlackApp.botId) {
      logger.debug('Skipping feedback storage - bot clicking its own buttons', {
        tenantId: tenantSlackApp.tenantId,
        userId,
        botId: tenantSlackApp.botId,
        messageId: messageTs,
        channelId,
        operation: 'bot-self-feedback-skip',
      });
      return;
    }

    // Store the feedback
    const slackMessageStorage = getSlackMessageStorage();
    const success = await slackMessageStorage.storeFeedback(tenantSlackApp.tenantId, {
      messageId: messageTs,
      channelId,
      userId,
      feedbackType,
    });

    if (success) {
      logger.info('Successfully stored feedback', {
        tenantId: tenantSlackApp.tenantId,
        feedbackType,
        userId,
        messageId: messageTs,
        channelId,
        operation: 'feedback-stored',
      });

      // Track analytics
      const analyticsTracker = getAnalyticsTracker();
      const channelName = await tenantSlackApp.getChannelName(channelId);
      await analyticsTracker.trackUserFeedback(
        tenantSlackApp.tenantId,
        feedbackType,
        messageTs,
        channelId,
        channelName,
        userId
      );
    } else {
      logger.warn('Failed to store feedback', {
        tenantId: tenantSlackApp.tenantId,
        feedbackType,
        userId,
        messageId: messageTs,
        channelId,
        operation: 'feedback-store-failed',
      });
    }
  } catch (error) {
    logger.error(
      'Error handling feedback button click',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        userId: event.user.id,
        messageTs: event.container.message_ts,
        channelId: event.container.channel_id,
        operation: 'feedback-button-error',
      }
    );
  }
}
