import { ButtonAction } from '@slack/bolt';
import { BasicEventArgs } from '../../types';
import { logger } from '../../utils/logger';
import { BlockActionEvent } from './buttonHandlers';
import { LinearClient } from '@linear/sdk';
import { getAnalyticsTracker } from '../../services/analyticsTracker';
import { linearService } from '../../services/linearService';
import { LinearOperationExecutor } from '@corporate-context/exponent-core';
import { LinearOperation, TaskAction } from '../../triage/types';
import {
  formatProactiveCreateMessage,
  formatProactiveUpdateMessage,
  buildSlackMessageLink,
} from '../../triage/formatters';
import { convertSlackToMarkdown } from '../../utils/textFormatting';

/**
 * Handle triage feedback button clicks (thumbs up/down)
 */
export async function onTriageFeedbackButtonClick(
  args: BasicEventArgs<BlockActionEvent>
): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    // Extract the button action
    const action = event.actions[0];
    if (!action) {
      logger.warn('No action in triage feedback button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    // Type guard: check if it's a button action
    if (!('action_id' in action) || !('value' in action)) {
      logger.warn('Invalid action type in triage feedback button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    const buttonAction = action as unknown as ButtonAction;

    // Validate action_id is a feedback button
    if (
      !['triage_feedback_positive', 'triage_feedback_negative'].includes(buttonAction.action_id)
    ) {
      logger.debug('Ignoring non-feedback button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'non-feedback-action',
      });
      return;
    }

    // Parse button value to get action type
    if (!buttonAction.value) {
      logger.warn('No value in triage feedback button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'missing-button-value',
      });
      return;
    }

    const buttonValue = JSON.parse(buttonAction.value);
    const { actionType, action_status } = buttonValue;

    // Determine feedback type from action_id
    const feedbackType =
      buttonAction.action_id === 'triage_feedback_positive' ? 'positive' : 'negative';

    // Post ephemeral confirmation message asynchronously (fire-and-forget for instant response)
    tenantSlackApp.client.chat
      .postEphemeral({
        channel: event.container.channel_id,
        user: event.user.id,
        thread_ts: event.container.message_ts,
        text: '✅ Feedback sent. Thank you!',
      })
      .catch((error) => {
        logger.error(
          'Error posting ephemeral feedback confirmation',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenantId: tenantSlackApp.tenantId,
            feedbackType,
            actionType,
            action_status,
            operation: 'triage-feedback-ephemeral-error',
          }
        );
      });

    // Track feedback to Amplitude asynchronously (no need to await)
    const analyticsTracker = getAnalyticsTracker();
    analyticsTracker
      .trackTriageFeedback(
        tenantSlackApp.tenantId,
        feedbackType,
        event.container.message_ts,
        event.container.channel_id,
        event.user.id,
        actionType,
        action_status
      )
      .catch((error) => {
        logger.error(
          'Error tracking triage feedback to analytics',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenantId: tenantSlackApp.tenantId,
            feedbackType,
            actionType,
            action_status,
            operation: 'triage-feedback-analytics-error',
          }
        );
      });

    logger.info('Triage feedback acknowledged', {
      tenantId: tenantSlackApp.tenantId,
      feedbackType,
      actionType,
      action_status,
      messageTs: event.container.message_ts,
      channelId: event.container.channel_id,
      userId: event.user.id,
      operation: 'triage-feedback-acknowledged',
    });
  } catch (error) {
    logger.error(
      'Error handling triage feedback button click',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        operation: 'triage-feedback-error',
      }
    );
  }
}

/**
 * Handle triage action button clicks (Delete ticket, Undo update)
 */
export async function onTriageButtonClick(args: BasicEventArgs<BlockActionEvent>): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    // Extract the button action
    const action = event.actions[0];
    if (!action) {
      logger.warn('No action in triage button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    // Type guard: check if it's a button action
    if (!('action_id' in action) || !('value' in action)) {
      logger.warn('Invalid action type in triage button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    const buttonAction = action as unknown as ButtonAction;

    // Validate action_id is a triage button
    if (!['triage_delete_ticket', 'triage_undo_update'].includes(buttonAction.action_id)) {
      logger.debug('Ignoring non-triage button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'non-triage-action',
      });
      return;
    }

    // Parse button value
    if (!buttonAction.value) {
      logger.warn('No value in triage button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'missing-button-value',
      });
      return;
    }

    const buttonValue = JSON.parse(buttonAction.value);
    const { linearIssueId, linearIssueUrl } = buttonValue;

    // Get valid Linear access token (with automatic refresh)
    const linearAccessToken = await linearService.getValidAccessToken(tenantSlackApp.tenantId);

    if (!linearAccessToken) {
      logger.error('No Linear access token found', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'missing-linear-access-token',
      });

      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: 'Unable to perform action',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: '❌ Unable to perform action: Linear access token not configured',
            },
          },
        ],
      });
      return;
    }

    const linearClient = new LinearClient({ accessToken: linearAccessToken });

    // Handle the action
    if (buttonAction.action_id === 'triage_delete_ticket') {
      await handleDeleteTicket(linearClient, linearIssueId, linearIssueUrl, event, tenantSlackApp);
    }
    // DISABLED: Undo update button - needs more robust implementation
    // else if (buttonAction.action_id === 'triage_undo_update') {
    //   await handleUndoUpdate(linearClient, linearIssueId, linearIssueUrl, event, tenantSlackApp);
    // }
  } catch (error) {
    logger.error(
      'Error handling triage button click',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        operation: 'triage-button-error',
      }
    );
  }
}

/**
 * Handle Delete ticket button action
 */
async function handleDeleteTicket(
  linearClient: LinearClient,
  linearIssueId: string,
  linearIssueUrl: string,
  event: BlockActionEvent,
  tenantSlackApp: {
    client: { chat: { postMessage: Function; update: Function } };
    tenantId: string;
    getChannelName: (channelId: string) => Promise<string>;
  }
): Promise<void> {
  try {
    // Get the issue and cancel it (Linear doesn't have true delete, we cancel/archive)
    const issue = await linearClient.issue(linearIssueId);

    if (!issue) {
      logger.warn('Linear issue not found', {
        linearIssueId,
        operation: 'delete-ticket-not-found',
      });

      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: 'Issue not found',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `~Created new Linear issue~\n❌ *Issue not found or already deleted*`,
            },
          },
        ],
      });
      return;
    }

    // Delete the issue (moves to trash)
    await issue.delete();

    // Update the original message to remove the button and show confirmation
    await tenantSlackApp.client.chat.update({
      channel: event.container.channel_id,
      ts: event.container.message_ts,
      text: `Ticket deleted`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `~Created new Linear issue~\n🗑️ *Ticket deleted*: <${linearIssueUrl}|View in Linear>`,
          },
        },
      ],
    });

    // Track successful delete in analytics
    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(event.container.channel_id);
    await analyticsTracker.trackTriageDeleteTicket(
      tenantSlackApp.tenantId,
      event.container.channel_id,
      channelName,
      event.user.id,
      event.container.message_ts,
      linearIssueId,
      linearIssueUrl,
      'success'
    );
  } catch (error) {
    logger.error(
      'Error deleting Linear ticket',
      error instanceof Error ? error : new Error(String(error)),
      {
        linearIssueId,
        operation: 'delete-ticket-error',
      }
    );

    await tenantSlackApp.client.chat.update({
      channel: event.container.channel_id,
      ts: event.container.message_ts,
      text: 'Failed to delete ticket',
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `:white_check_mark: *Created new Linear issue*\n<${linearIssueUrl}|View in Linear>\n\n❌ *Failed to delete ticket*. Please try again or delete manually in Linear.`,
          },
        },
      ],
    });

    // Track failed delete in analytics
    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(event.container.channel_id);
    await analyticsTracker.trackTriageDeleteTicket(
      tenantSlackApp.tenantId,
      event.container.channel_id,
      channelName,
      event.user.id,
      event.container.message_ts,
      linearIssueId,
      linearIssueUrl,
      'error'
    );
  }
}

/**
 * Handle Undo update button action
 * DISABLED: Needs more robust implementation to store previous description
 */
// @ts-expect-error - Function disabled but kept for future implementation
// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function handleUndoUpdate(
  linearClient: LinearClient,
  linearIssueId: string,
  linearIssueUrl: string,
  event: BlockActionEvent,
  tenantSlackApp: {
    client: { chat: { postMessage: Function; update: Function } };
    tenantId: string;
    getChannelName: (channelId: string) => Promise<string>;
  }
): Promise<void> {
  try {
    // Get the current issue
    const issue = await linearClient.issue(linearIssueId);

    if (!issue) {
      logger.warn('Linear issue not found', {
        linearIssueId,
        operation: 'undo-update-not-found',
      });

      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: 'Issue not found',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `~Context added to existing Linear issue~\n❌ *Issue not found*`,
            },
          },
        ],
      });
      return;
    }

    // Get current description
    const currentDescription = issue.description || '';

    // Find and remove the "Duplicate Reports" section
    // This is more robust than exact text matching since Linear may transform markdown
    const duplicateReportsDivider = '\n\n---\n\n## Duplicate Reports';
    const dividerIndex = currentDescription.lastIndexOf(duplicateReportsDivider);

    let newDescription = currentDescription;
    const foundDivider = dividerIndex !== -1;

    if (foundDivider) {
      // Remove everything from the divider onward
      newDescription = currentDescription.substring(0, dividerIndex).trim();
    } else {
      logger.warn('Duplicate Reports divider not found - no changes made', {
        linearIssueId,
        currentDescriptionLength: currentDescription.length,
        operation: 'undo-update-divider-not-found',
      });
    }

    // Update the issue with the reverted description
    await issue.update({ description: newDescription });

    // Update the original message to remove the button and show confirmation
    await tenantSlackApp.client.chat.update({
      channel: event.container.channel_id,
      ts: event.container.message_ts,
      text: `Update undone`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `~Context added to existing Linear issue~\n↩️ *Update undone*: <${linearIssueUrl}|View in Linear>`,
          },
        },
      ],
    });

    // Track successful undo in analytics
    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(event.container.channel_id);
    await analyticsTracker.trackTriageUndoUpdate(
      tenantSlackApp.tenantId,
      event.container.channel_id,
      channelName,
      event.user.id,
      event.container.message_ts,
      linearIssueId,
      linearIssueUrl,
      'success'
    );
  } catch (error) {
    logger.error(
      'Error undoing Linear update',
      error instanceof Error ? error : new Error(String(error)),
      {
        linearIssueId,
        operation: 'undo-update-error',
      }
    );

    await tenantSlackApp.client.chat.update({
      channel: event.container.channel_id,
      ts: event.container.message_ts,
      text: 'Failed to undo update',
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `:white_check_mark: *Context added to existing Linear issue*\n<${linearIssueUrl}|View in Linear>\n\n❌ *Failed to undo update*. Please try again or edit manually in Linear.`,
          },
        },
      ],
    });

    // Track failed undo in analytics
    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(event.container.channel_id);
    await analyticsTracker.trackTriageUndoUpdate(
      tenantSlackApp.tenantId,
      event.container.channel_id,
      channelName,
      event.user.id,
      event.container.message_ts,
      linearIssueId,
      linearIssueUrl,
      'error'
    );
  }
}

/**
 * Handle non-proactive triage action button clicks (Create/Update ticket)
 */
export async function onNonProactiveTriageButtonClick(
  args: BasicEventArgs<BlockActionEvent>
): Promise<void> {
  const { event, tenantSlackApp } = args;

  try {
    // Extract the button action
    const action = event.actions[0];
    if (!action) {
      logger.warn('No action in non-proactive triage button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    // Type guard: check if it's a button action
    if (!('action_id' in action) || !('value' in action)) {
      logger.warn('Invalid action type in non-proactive triage button event', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'invalid-action',
      });
      return;
    }

    const buttonAction = action as unknown as ButtonAction;

    // Validate action_id is an execute button
    if (!['triage_execute_create', 'triage_execute_update'].includes(buttonAction.action_id)) {
      logger.debug('Ignoring non-execute button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'non-execute-action',
      });
      return;
    }

    // Parse button value
    if (!buttonAction.value) {
      logger.warn('No value in non-proactive triage button action', {
        tenantId: tenantSlackApp.tenantId,
        actionId: buttonAction.action_id,
        operation: 'missing-button-value',
      });
      return;
    }

    const buttonValue = JSON.parse(buttonAction.value);
    const { action: taskAction, title, linearTeamId, linearIssueId } = buttonValue;

    // Get valid Linear access token (with automatic refresh)
    const linearAccessToken = await linearService.getValidAccessToken(tenantSlackApp.tenantId);

    if (!linearAccessToken) {
      logger.error('No Linear access token found', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'missing-linear-access-token',
      });

      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: 'Unable to perform action',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: '❌ Unable to perform action: Linear access token not configured',
            },
          },
        ],
      });
      return;
    }

    // Validate event.message exists and has blocks
    if (!event.message || !('blocks' in event.message) || !Array.isArray(event.message.blocks)) {
      logger.error('Event message or blocks missing', {
        tenantId: tenantSlackApp.tenantId,
        operation: 'missing-message-blocks',
      });
      return;
    }

    const messageBlocks = event.message.blocks as unknown[];

    // Extract description/append from message blocks
    let description: string | undefined;
    let descriptionAppend: string | undefined;

    if (taskAction === TaskAction.CREATE) {
      // Find block with block_id: 'triage_description'
      const descriptionBlock = messageBlocks.find(
        (b): b is Record<string, unknown> =>
          typeof b === 'object' &&
          b !== null &&
          'block_id' in b &&
          (b as Record<string, unknown>).block_id === 'triage_description'
      );
      if (descriptionBlock && 'text' in descriptionBlock && descriptionBlock.text) {
        const slackText =
          typeof descriptionBlock.text === 'string'
            ? descriptionBlock.text
            : typeof descriptionBlock.text === 'object' &&
                descriptionBlock.text !== null &&
                'text' in descriptionBlock.text
              ? ((descriptionBlock.text as Record<string, unknown>).text as string)
              : '';
        // Strip "**Description:**\n" prefix and convert from Slack to markdown
        const cleanedText = slackText.replace(/^\*\*Description:\*\*\n/, '');
        description = convertSlackToMarkdown(cleanedText);
      }
    } else if (taskAction === TaskAction.UPDATE) {
      // Find block with block_id: 'triage_append_context'
      const appendBlock = messageBlocks.find(
        (b): b is Record<string, unknown> =>
          typeof b === 'object' &&
          b !== null &&
          'block_id' in b &&
          (b as Record<string, unknown>).block_id === 'triage_append_context'
      );
      if (appendBlock && 'text' in appendBlock && appendBlock.text) {
        const slackText =
          typeof appendBlock.text === 'string'
            ? appendBlock.text
            : typeof appendBlock.text === 'object' &&
                appendBlock.text !== null &&
                'text' in appendBlock.text
              ? ((appendBlock.text as Record<string, unknown>).text as string)
              : '';
        // Strip "**Context to add:**\n" prefix and convert from Slack to markdown
        const cleanedText = slackText.replace(/^\*\*Context to add:\*\*\n/, '');
        descriptionAppend = convertSlackToMarkdown(cleanedText);
      }
    }

    // Build LinearOperation
    const operation: LinearOperation = {
      action: taskAction,
      confidence: 100, // User explicitly clicked button, so 100% confidence
      reasoning: 'User manually approved and executed the suggested action',
      ...(taskAction === TaskAction.CREATE
        ? {
            createData: {
              title: title || '',
              description: description || '',
            },
          }
        : {}),
      ...(taskAction === TaskAction.UPDATE
        ? {
            updateData: {
              issueId: linearIssueId || '',
              descriptionAppend: descriptionAppend || '',
            },
          }
        : {}),
    };

    // Execute the operation
    const executor = new LinearOperationExecutor(linearAccessToken, linearTeamId || '');
    const result = await executor.executeOperation(operation);

    logger.info('[Non-Proactive Triage] Operation executed', {
      tenantId: tenantSlackApp.tenantId,
      action: taskAction,
      success: result.success,
      linearIssueId: result.linearIssueId,
    });

    // Track analytics
    if (result.success) {
      const analyticsTracker = getAnalyticsTracker();
      const channelName = await tenantSlackApp.getChannelName(event.container.channel_id);
      await analyticsTracker.trackTriageDecisionMade(
        tenantSlackApp.tenantId,
        event.container.channel_id,
        channelName,
        event.container.message_ts,
        linearTeamId || '',
        taskAction,
        result.linearIssueId,
        result.linearIssueUrl,
        result.linearIssueTitle
      );
    }

    // Update message with proactive formatter
    let blocks;
    if (taskAction === TaskAction.CREATE) {
      blocks = formatProactiveCreateMessage(result);
    } else if (taskAction === TaskAction.UPDATE) {
      blocks = formatProactiveUpdateMessage(result);
    }

    if (blocks) {
      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: result.success ? 'Action completed' : 'Action failed',
        blocks,
      });
    }

    // Add Slack link attachment for CREATE operations
    if (
      taskAction === TaskAction.CREATE &&
      result.success &&
      result.linearIssueId &&
      'thread_ts' in event.message &&
      event.message.thread_ts
    ) {
      const slackLink = buildSlackMessageLink(
        tenantSlackApp.workspaceTeamId,
        event.container.channel_id,
        event.message.ts,
        event.message.thread_ts
      );
      await executor.createAttachment(result.linearIssueId, 'Original Slack Discussion', slackLink);
    }

    logger.info('[Non-Proactive Triage] Button click handled successfully', {
      tenantId: tenantSlackApp.tenantId,
      action: taskAction,
      messageTs: event.container.message_ts,
    });
  } catch (error) {
    logger.error(
      'Error handling non-proactive triage button click',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId: tenantSlackApp.tenantId,
        operation: 'non-proactive-triage-button-error',
      }
    );

    // Try to update the message with an error
    try {
      await tenantSlackApp.client.chat.update({
        channel: event.container.channel_id,
        ts: event.container.message_ts,
        text: 'Error performing action',
        blocks: [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: "❌ I'm unable to perform this action at this time. Please try again later.",
            },
          },
        ],
      });
    } catch (updateError) {
      logger.error(
        'Failed to update message with error',
        updateError instanceof Error ? updateError : new Error(String(updateError)),
        {
          tenantId: tenantSlackApp.tenantId,
          operation: 'update-error-message-failed',
        }
      );
    }
  }
}
