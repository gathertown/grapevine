import { logger } from './utils/logger';
import {
  formatSlackMessages,
  postTriageResultToSlack,
  postTriageResultToSlackQualityDebug,
  buildSlackMessageLink,
  SlackMessage,
  formatNonProactiveCreateMessage,
  formatNonProactiveUpdateMessage,
  formatNonProactiveSkipMessage,
} from './triage/formatters';
import { TaskAction } from './triage/types';
import { TriageAgentStrategy } from './triage/TriageAgentStrategy';
import { LinearOperationExecutor } from '@corporate-context/exponent-core';
import { switchEnv } from '@corporate-context/backend-common';
import { GenericMessageEvent } from '@slack/bolt';
import { TenantSlackApp } from './TenantSlackApp';
import { linearService } from './services/linearService';
import { getAnalyticsTracker } from './services/analyticsTracker';
import { tenantConfigManager } from './config/tenantConfigManager';
import type { KnownBlock } from '@slack/types';

/**
 * Check if a channel is in quality debug mode and get its mirror channel
 * @param channelId - Channel ID to check
 * @returns Mirror channel ID if in quality debug mode, undefined otherwise
 */
export function getQualityDebugMirrorChannel(channelId: string): string | undefined {
  const qualityDebugChannels: { [key: string]: string | undefined } = switchEnv({
    local: {},
    staging: {},
    production: {},
  });
  return qualityDebugChannels[channelId];
}

/**
 * Fetch messages from Slack (either thread or single message)
 * @param message - The message event
 * @param tenantSlackApp - Tenant Slack app instance
 * @returns Array of Slack messages with user field
 */
async function fetchSlackMessages(
  message: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp
): Promise<SlackMessage[]> {
  const slackClient = tenantSlackApp.client;

  let allMessages: Array<Record<string, unknown>> = [];

  if (message.thread_ts) {
    // Fetch thread
    const result = await slackClient.conversations.replies({
      channel: message.channel,
      ts: message.thread_ts,
    });
    allMessages = (result.messages || []) as Array<Record<string, unknown>>;
  } else {
    // Fetch single message
    const result = await slackClient.conversations.history({
      channel: message.channel,
      latest: message.ts,
      limit: 1,
      inclusive: true,
    });
    allMessages = (result.messages || []) as Array<Record<string, unknown>>;
  }

  // Filter messages and log any that are filtered out
  const filteredMessages: SlackMessage[] = [];
  const filteredOutMessages: Array<Record<string, unknown>> = [];

  for (const msg of allMessages) {
    if (msg.user || msg.bot_id) {
      filteredMessages.push(msg as unknown as SlackMessage);
    } else {
      filteredOutMessages.push(msg);
    }
  }

  // Log if we filtered out any messages
  if (filteredOutMessages.length > 0) {
    logger.info('[Triage] Filtered out messages without user or bot_id', {
      channelId: message.channel,
      messageTs: message.ts,
      totalMessages: allMessages.length,
      filteredOutCount: filteredOutMessages.length,
      filteredOutMessages: filteredOutMessages.map((m) => ({
        ts: m.ts,
        subtype: m.subtype,
        type: m.type,
        text: typeof m.text === 'string' ? m.text?.substring(0, 100) : undefined,
      })),
    });
  }

  return filteredMessages;
}

export async function processTriageChannelMessage(
  message: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  linearTeamId: string | null,
  qualityDebugChannelId?: string
): Promise<void> {
  const slackClient = tenantSlackApp.client;
  const threadTs = message.thread_ts || message.ts;

  try {
    // Skip if message is from the bot itself
    if (message.user === tenantSlackApp.botId) {
      logger.info('[Triage] Skipping message from ourselves');
      return;
    }

    await tenantSlackApp.addProcessingReaction(message.channel, message.ts);

    // Fetch messages (either thread or single message)
    const messages = await fetchSlackMessages(message, tenantSlackApp);

    if (messages.length === 0) {
      logger.warn('[Triage] No messages found', {
        channelId: message.channel,
        messageTs: message.ts,
      });
      return;
    }

    // Format messages for triage
    const slackDocument = await formatSlackMessages(
      messages,
      slackClient,
      message.channel,
      tenantSlackApp.botToken,
      tenantSlackApp.tenantId
    );

    // Get valid Linear access token only if we have a linearTeamId (needed for execution)
    let linearAccessToken: string | null = null;
    if (linearTeamId) {
      linearAccessToken = await linearService.getValidAccessToken(tenantSlackApp.tenantId);

      if (!linearAccessToken) {
        logger.warn(
          `[Triage] Missing required Linear configuration for tenant ${tenantSlackApp.tenantId}: LINEAR_ACCESS_TOKEN`
        );
        await slackClient.chat.postMessage({
          channel: message.channel,
          thread_ts: threadTs,
          text: 'A Linear access token with write access is required for triage.',
        });
        await tenantSlackApp.removeProcessingReaction(message.channel, message.ts);
        return;
      }
    }

    logger.info('[Triage] Processing message', {
      channelId: message.channel,
      linearTeamId,
      qualityDebugChannelId,
      tenantId: tenantSlackApp.tenantId,
    });

    // Run triage agent
    const strategy = new TriageAgentStrategy();
    const { operations, triageAnalysis } = await strategy.process(
      slackDocument,
      message.user,
      tenantSlackApp
    );

    logger.info('[Triage] Triage analysis complete');

    // If in quality debug mode, additionally x-post to mirror channel for us to debug
    if (qualityDebugChannelId) {
      await postTriageResultToSlackQualityDebug(
        tenantSlackApp,
        qualityDebugChannelId,
        threadTs,
        triageAnalysis,
        message.channel,
        message.ts,
        slackDocument.content
      );

      logger.info('[Triage] Quality debug workflow complete', {
        channelId: message.channel,
        messageTs: message.ts,
        qualityDebugChannelId,
      });
    }

    // Validate that the original message still exists before posting results
    const messageExists = await tenantSlackApp.checkMessageExists(
      message.channel,
      message.ts,
      message.thread_ts
    );

    if (!messageExists) {
      logger.info(
        '[Triage] Skipping result posting - original message was deleted during processing',
        {
          channelId: message.channel,
          messageTs: message.ts,
          threadTs: message.thread_ts,
          tenantId: tenantSlackApp.tenantId,
        }
      );
      await tenantSlackApp.removeProcessingReaction(message.channel, message.ts);
      return;
    }

    // Check proactive mode setting
    const isProactive = await tenantConfigManager.getTriageProactiveMode(tenantSlackApp.tenantId);

    logger.info('[Triage] Proactive mode check', {
      isProactive,
      tenantId: tenantSlackApp.tenantId,
    });

    if (linearTeamId && linearAccessToken) {
      if (isProactive) {
        // PROACTIVE MODE: Execute operations immediately and post results
        const executor = new LinearOperationExecutor(linearAccessToken, linearTeamId);
        const executionSummary = await executor.executeOperations(operations);

        logger.info('[Triage] Linear operations executed', {
          totalOperations: executionSummary.totalOperations,
          successful: executionSummary.successful,
          failed: executionSummary.failed,
        });

        // Track successful triage decisions
        const channelName = await tenantSlackApp.getChannelName(message.channel);
        const analyticsTracker = getAnalyticsTracker();
        for (const result of executionSummary.results) {
          if (result.success) {
            await analyticsTracker.trackTriageDecisionMade(
              tenantSlackApp.tenantId,
              message.channel,
              channelName,
              message.ts,
              linearTeamId,
              result.operation.action,
              result.linearIssueId,
              result.linearIssueUrl,
              result.linearIssueTitle
            );
          }
        }

        // Post results back to Slack
        await postTriageResultToSlack(
          tenantSlackApp,
          message.channel,
          threadTs,
          triageAnalysis,
          executionSummary
        );

        // Add Slack link attachments for CREATE operations
        for (const result of executionSummary.results) {
          if (
            result.operation.action === TaskAction.CREATE &&
            result.success &&
            result.linearIssueId
          ) {
            const slackLink = buildSlackMessageLink(
              tenantSlackApp.workspaceTeamId,
              message.channel,
              message.ts,
              message.thread_ts
            );
            await executor.createAttachment(
              result.linearIssueId,
              'Original Slack Discussion',
              slackLink
            );
          }
        }
      } else {
        // NON-PROACTIVE MODE: Show analysis with buttons, don't execute operations yet
        if (!triageAnalysis) {
          logger.warn('[Triage] No triage analysis available for non-proactive mode');
          return;
        }

        const operation = triageAnalysis.operation;
        let blocks: KnownBlock[] = [];

        if (operation.action === TaskAction.CREATE) {
          blocks = formatNonProactiveCreateMessage(triageAnalysis, linearTeamId);
        } else if (operation.action === TaskAction.UPDATE) {
          blocks = formatNonProactiveUpdateMessage(triageAnalysis);
        } else if (operation.action === TaskAction.SKIP) {
          blocks = formatNonProactiveSkipMessage(triageAnalysis);
        }

        if (blocks.length > 0) {
          await tenantSlackApp.postMessage({
            channel: message.channel,
            thread_ts: threadTs,
            text: 'Triage analysis complete',
            blocks,
          });
        }

        logger.info('[Triage] Non-proactive message posted', {
          action: operation.action,
          channelId: message.channel,
        });
      }
    }

    await tenantSlackApp.removeProcessingReaction(message.channel, message.ts);

    logger.info('[Triage] Triage workflow complete', {
      channelId: message.channel,
      messageTs: message.ts,
      qualityDebugChannelId,
    });
  } catch (error) {
    logger.error('[Triage] Error processing triage workflow', {
      channelId: message.channel,
      messageTs: message.ts,
      qualityDebugChannelId,
      error: error instanceof Error ? error.message : JSON.stringify(error),
    });

    await tenantSlackApp.removeProcessingReaction(message.channel, message.ts);
    if (threadTs) {
      await slackClient.chat.postMessage({
        channel: message.channel,
        thread_ts: threadTs,
        text: "I'm unable to generate a response at this time.",
      });
    } else {
      logger.error(
        `[Triage] Tried to post a generic error message but threadTs $${threadTs} is falsey`
      );
    }
  }
}
