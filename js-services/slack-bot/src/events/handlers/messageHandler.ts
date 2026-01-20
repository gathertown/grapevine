import { MessageEventArgs } from '../../types';
import { isBotMentioned, isDMChannel } from '../../common';
import { logger, LogContext } from '../../utils/logger';
import {
  processDirectMessage,
  processDMThreadOrChannelThreadMention,
  processChannelMention,
  processChannelQuestion,
} from '../../question';
import { getQualityDebugMirrorChannel, processTriageChannelMessage } from '../../triage';
import { getLinearTeamIdForTriageChannel } from '../../triage/linearTeamMappings';

export async function handleMessage(args: MessageEventArgs): Promise<void> {
  const { message, tenantSlackApp } = args;

  return LogContext.run(
    {
      tenant_id: tenantSlackApp.tenantId,
      channelId: message.channel,
      userId: message.user,
      messageTs: message.ts,
      threadTs: message.thread_ts,
    },
    async () => {
      // A message is top-level if it has no thread_ts OR if thread_ts equals ts (root of a thread)
      const isTopLevelMessage = message.thread_ts === undefined || message.thread_ts === message.ts;

      // Check if this channel has a Linear team mapping (used for triage workflow)
      // This serves as both the whitelist check and gets the team ID for later use
      const linearTeamId = await getLinearTeamIdForTriageChannel(
        message.channel,
        tenantSlackApp.tenantId
      );

      // Check if this channel is whitelisted for quality debug mode
      const qualityDebugChannelId = getQualityDebugMirrorChannel(message.channel);

      const allowedSubtypes = ['thread_broadcast', 'file_share', 'bot_message'];
      const hasAllowedSubtype = !message.subtype || allowedSubtypes.includes(message.subtype);
      const isBotMentionedInMessage = isBotMentioned(message.text || '', tenantSlackApp.botId);
      const isOurBot = message.user === tenantSlackApp.botId;

      // Triage decision: Route to triage workflow if ALL conditions are met:
      // 1. Channel has a Linear team mapping OR is whitelisted for quality debug
      // 2. Message is top-level, not a thread reply (isTopLevelMessage)
      // 3. Bot is not mentioned - if mentioned, route to Q&A instead (!isBotMentionedInMessage)
      // 4. Message is not from our own bot - prevents message_changed loops (!isOurBot)
      // 5. Subtype is allowed - blocks message_changed and other system events (hasAllowedSubtype)
      const shouldRouteTriage =
        (linearTeamId || qualityDebugChannelId) &&
        isTopLevelMessage &&
        !isBotMentionedInMessage &&
        !isOurBot &&
        hasAllowedSubtype;

      logger.info('Message received - triage decision', {
        channel: message.channel,
        messageTs: message.ts,
        userId: message.user,
        subtype: message.subtype,
        linearTeamId,
        qualityDebugChannelId,
        isTopLevelMessage,
        isBotMentioned: isBotMentionedInMessage,
        isOurBot,
        hasAllowedSubtype,
        shouldRouteTriage,
        operation: 'triage-decision',
      });

      if (shouldRouteTriage) {
        // Triage workflow - handle both linear team and quality debug flows
        await processTriageChannelMessage(
          message,
          tenantSlackApp,
          linearTeamId,
          qualityDebugChannelId
        );
        return;
      }

      // Skip processing for bot messages and system messages
      if (!message.user || message.bot_id) {
        logger.debug('handleMessage: Skipping bot/system message (no user ID or bot message)', {
          operation: 'message-skip',
        });
        return;
      }

      // Skip messages from Slackbot to prevent bot-to-bot conversations
      if (message.user === 'USLACKBOT') {
        logger.debug('handleMessage: Skipping message from Slackbot', {
          operation: 'message-skip-slackbot',
        });
        return;
      }

      // Skip messages with subtypes, except the following
      const respond_subtypes = ['thread_broadcast', 'file_share'];
      if (message.subtype && !respond_subtypes.includes(message.subtype)) {
        logger.debug(`handleMessage: Skipping message with subtype '${message.subtype}'`, {
          subtype: message.subtype,
          operation: 'message-skip',
        });
        return;
      }

      try {
        try {
          const channelName = await tenantSlackApp.getChannelName(message.channel);
          const userName = await tenantSlackApp.getUserName(message.user);
          logger.info(`Processing message in #${channelName} from ${userName}`, {
            operation: 'slack-event',
          });
        } catch {
          // Fallback to IDs if name resolution fails
          logger.info('Processing message', { operation: 'slack-event' });
        }

        // Handle different message contexts
        if (isDMChannel(message)) {
          // Direct message
          if (message.thread_ts) {
            await processDMThreadOrChannelThreadMention(message, tenantSlackApp);
          } else {
            await processDirectMessage(message, tenantSlackApp);
          }
        } else if (message.thread_ts && isBotMentioned(message.text || '', tenantSlackApp.botId)) {
          // Thread mention - check if mentions from non-members are blocked
          if (await tenantSlackApp.shouldProcessMentionFromUser(message.user, message.channel)) {
            await processDMThreadOrChannelThreadMention(
              message,
              tenantSlackApp,
              linearTeamId || undefined
            );
          } else {
            logger.info('Skipping thread mention from non-member user (blocked by tenant config)', {
              channelId: message.channel,
              userId: message.user,
              operation: 'mention-blocked-non-member',
            });
          }
        } else if (isBotMentioned(message.text || '', tenantSlackApp.botId)) {
          // Channel mention - check if mentions from non-members are blocked
          if (await tenantSlackApp.shouldProcessMentionFromUser(message.user, message.channel)) {
            await processChannelMention(message, tenantSlackApp, linearTeamId || undefined);
          } else {
            logger.info(
              'Skipping channel mention from non-member user (blocked by tenant config)',
              {
                channelId: message.channel,
                userId: message.user,
                operation: 'mention-blocked-non-member',
              }
            );
          }
        } else if (
          !message.thread_ts &&
          (await tenantSlackApp.shouldProcessChannel(message.channel))
        ) {
          // Regular channel message (potential question)
          await processChannelQuestion(message, tenantSlackApp);
        }
      } catch (error) {
        logger.error(
          'Error processing message',
          error instanceof Error ? error : new Error(String(error)),
          { operation: 'message-processing' }
        );
        throw error;
      }
    }
  );
}
