/**
 * Formatters for Slack messages and triage results
 */

import { WebClient } from '@slack/web-api';
import type { KnownBlock } from '@slack/types';
import {
  SlackDocument,
  ExecutionSummary,
  LinearTicketInfo,
  ExecutionResult,
  TriageAnalysis,
  TaskAction,
  LinearOperation,
} from './types';
import { extractLinearIdFromUrl, buildLinearUrl } from '../utils/linearUrl';
import { buildDividerBlock, buildSectionBlock } from '../utils/slackBlocks';
import { downloadSlackFiles, type SlackFile } from '../common';
import type { FileAttachment } from '../types';
import { logger } from '../utils/logger';
import type { TenantSlackApp } from '../TenantSlackApp';
import { linearService } from '../services/linearService';
import { LinearClient } from '@linear/sdk';

/**
 * Slack message attachment
 */
export interface SlackLinearAttachment {
  from_url?: string;
  id?: number;
}

/**
 * Slack message from conversations.replies or conversations.history
 */
export interface SlackMessage {
  user?: string;
  bot_id?: string;
  username?: string;
  subtype?: string;
  text?: string;
  ts: string;
  files?: Array<SlackFile>;
  attachments?: SlackLinearAttachment[];
}

/**
 * Extract Linear ticket ID from Slack attachment
 * Looks for Linear URLs in from_url, title_link, fields, or text
 */
function extractLinearTicketIdFromAttachment(attachment: SlackLinearAttachment): string | null {
  // Check from_url first (most common for Linear Asks bot)
  if (attachment.from_url) {
    const match = attachment.from_url.match(/linear\.app\/[^/]+\/issue\/([A-Z]+-\d+)/);
    if (match) return match[1];
  }

  return null;
}

/**
 * Fetch Linear ticket details from Linear API
 */
async function fetchLinearTicketDetails(
  ticketId: string,
  tenantId: string
): Promise<LinearTicketInfo | null> {
  try {
    // Get Linear access token for this tenant
    const accessToken = await linearService.getValidAccessToken(tenantId);
    if (!accessToken) {
      logger.warn('No Linear access token available for tenant', { tenantId });
      return null;
    }

    // Create Linear client and search for issue by identifier (e.g., "CUR-420")
    const linearClient = new LinearClient({ accessToken });

    // This searches across all text fields including the identifier
    const searchResults = await linearClient.searchIssues(ticketId);

    // Find exact match on identifier
    const issuesArray = await searchResults.nodes;
    const issue = issuesArray.find((i) => i.identifier === ticketId);

    if (!issue) {
      logger.warn('Linear ticket not found', { ticketId, resultsCount: issuesArray.length });
      return null;
    }

    return {
      ticketId: issue.identifier,
      ticketUrl: issue.url,
      description: issue.description || undefined,
      title: issue.title,
    };
  } catch (error) {
    logger.error(
      'Failed to fetch Linear ticket details',
      error instanceof Error ? error : new Error(String(error)),
      { ticketId }
    );
    return null;
  }
}

/**
 * Format Slack messages into a SlackDocument for triage
 *
 * @param messages - Array of Slack messages
 * @param client - Slack client for resolving user names
 * @param channelId - Channel ID for context
 * @param botToken - Slack bot token for downloading files
 * @param tenantId - Tenant ID for fetching Linear ticket details
 * @returns SlackDocument ready for triage
 */
export async function formatSlackMessages(
  messages: SlackMessage[],
  client: WebClient,
  channelId: string,
  botToken: string,
  tenantId: string
): Promise<SlackDocument> {
  // Build user lookup map
  const userIds = [
    ...new Set(messages.map((m) => m.user).filter((id): id is string => id !== undefined)),
  ];
  const userLookup = new Map<string, string>();

  for (const userId of userIds) {
    try {
      const userInfo = await client.users.info({ user: userId });
      if (userInfo.user) {
        userLookup.set(userId, userInfo.user.real_name || userInfo.user.name || userId);
      }
    } catch {
      userLookup.set(userId, userId);
    }
  }

  // Collect all files from all messages
  const allFiles: FileAttachment[] = [];
  for (const msg of messages) {
    if (msg.files && msg.files.length > 0) {
      const downloadedFiles = await downloadSlackFiles(msg.files, botToken);
      allFiles.push(...downloadedFiles);
    }
  }

  // Check if "Linear Asks" is a participant
  const participants = Array.from(userLookup.values());
  const hasLinearAsks = participants.some((name) => name === 'Linear Asks');

  logger.info('Checking for Linear Asks participant', {
    hasLinearAsks,
    participants,
  });

  // If Linear Asks is present, check for Linear ticket attachments in the top-level message
  let linearTicketInfo: LinearTicketInfo | undefined;
  if (hasLinearAsks && messages.length > 0) {
    const topLevelMessage = messages[0];
    if (topLevelMessage.attachments && topLevelMessage.attachments.length > 0) {
      logger.info('Found attachments in top-level message', {
        attachments: topLevelMessage.attachments,
        attachmentCount: topLevelMessage.attachments.length,
      });

      // Look for Linear ticket ID in attachments
      for (const attachment of topLevelMessage.attachments) {
        const ticketId = extractLinearTicketIdFromAttachment(attachment);
        if (ticketId) {
          logger.info('Found Linear ticket ID in attachment', { ticketId });

          // Fetch ticket details from Linear API
          const ticketDetails = await fetchLinearTicketDetails(ticketId, tenantId);
          if (ticketDetails) {
            linearTicketInfo = ticketDetails;
            logger.info('Successfully fetched Linear ticket details', {
              ticketId: ticketDetails.ticketId,
              hasDescription: !!ticketDetails.description,
            });
            break; // Use the first ticket found
          }
        }
      }
    }
  }

  // Format messages
  const formattedMessages = messages
    .map((msg) => {
      // For regular user messages, look up the user name
      // For bot messages, use the username field
      const userName = msg.user
        ? userLookup.get(msg.user) || msg.user
        : msg.username || msg.bot_id || 'Unknown';
      const timestamp = new Date(Number(msg.ts) * 1000).toISOString();
      const fileNote =
        msg.files && msg.files.length > 0
          ? ` [Attached ${msg.files.length} file(s): ${msg.files.map((f) => f.name).join(', ')}]`
          : '';
      return `[${timestamp}] ${userName}: ${msg.text || ''}${fileNote}`;
    })
    .join('\n\n');

  return {
    channel: channelId,
    content: formattedMessages,
    date: new Date().toISOString(),
    participants,
    files: allFiles.length > 0 ? allFiles : undefined,
    linearTicketInfo,
  };
}

/**
 * Build Slack message link
 *
 * @param teamId - Slack team/workspace ID
 * @param channelId - Channel ID
 * @param messageTs - Message timestamp
 * @param threadTs - Thread timestamp
 * @returns Slack message link
 */
export function buildSlackMessageLink(
  teamId: string,
  channelId: string,
  messageTs: string,
  threadTs?: string
): string {
  const tsWithoutDot = messageTs.replace('.', '');
  return `https://app.slack.com/client/${teamId}/${channelId}/p${tsWithoutDot}${
    threadTs ? `?thread_ts=${threadTs}` : ''
  }`;
}

/**
 * Post triage result to Slack in quality debug mode (no action buttons, no operations executed)
 *
 * @param tenantSlackApp - Tenant Slack app instance
 * @param channel - Channel ID (usually the mirror channel)
 * @param threadTs - Thread timestamp
 * @param triageAnalysis - Triage analysis from agent
 * @param originalChannelId - Original channel ID where the message was posted
 * @param originalMessageTs - Original message timestamp
 * @param originalMessageContent - The formatted content of the original message/thread
 */
export async function postTriageResultToSlackQualityDebug(
  tenantSlackApp: TenantSlackApp,
  channel: string,
  threadTs: string,
  triageAnalysis: TriageAnalysis | undefined,
  originalChannelId: string,
  originalMessageTs: string,
  originalMessageContent: string
): Promise<void> {
  const blocks: KnownBlock[] = [];

  // Get channel name
  let channelName = originalChannelId;
  try {
    const channelInfo = await tenantSlackApp.client.conversations.info({
      channel: originalChannelId,
    });
    if (channelInfo.channel?.name) {
      channelName = `#${channelInfo.channel.name}`;
    }
  } catch (error) {
    // Fall back to channel ID if we can't get the name
    logger.warn('Failed to fetch original slack channel name', { error });
  }

  // Add context header
  blocks.push(
    buildSectionBlock(
      `${channelName} [View message](https://slack.com/archives/${originalChannelId}/p${originalMessageTs.replace('.', '')})`
    )
  );

  // Add original message content as quote block
  const quotedContent = originalMessageContent
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');

  blocks.push(buildSectionBlock(quotedContent));

  blocks.push(buildDividerBlock());

  // Show the operation that would be performed
  const operation = triageAnalysis?.operation;

  if (operation?.action === TaskAction.CREATE) {
    const createData = operation.createData;
    if (createData) {
      blocks.push(
        buildSectionBlock(
          `:white_check_mark: **Would create new Linear issue**\n**${createData.title}**`
        )
      );

      if (createData.description?.trim()) {
        blocks.push(buildSectionBlock(`**Description:**\n${createData.description}`));
      }
    }
  } else if (operation?.action === TaskAction.SKIP && operation.skipData) {
    blocks.push(
      buildSectionBlock(
        `:information_source: **${
          operation.skipData.issueId
            ? 'Would skip - duplicate found'
            : 'Would skip - no issue needed'
        }**`
      )
    );

    if (operation.skipData.issueId) {
      const duplicateIssue = triageAnalysis?.relatedTickets.find(
        (ticket) => ticket.ticketId === operation.skipData?.issueId
      );

      if (duplicateIssue) {
        const confidencePercent = Math.round(duplicateIssue.confidence * 100);
        const ticketLink = buildLinearUrl(duplicateIssue.ticketId, duplicateIssue.url);
        blocks.push(
          buildSectionBlock(
            `[${duplicateIssue.ticketId}: ${duplicateIssue.title}](${ticketLink}) (${confidencePercent}% match)`
          )
        );
      }
    } else if (operation.skipData.reason) {
      blocks.push(buildSectionBlock(`**Reason:** ${operation.skipData.reason}`));
    }
  } else if (operation?.action === TaskAction.UPDATE && operation.updateData) {
    blocks.push(
      buildSectionBlock(
        `:information_source: **Would add context to existing Linear issue** [${operation.updateData.issueId}](${buildLinearUrl(
          operation.updateData.issueId,
          ''
        )})`
      )
    );

    if (operation.updateData.descriptionAppend?.trim()) {
      blocks.push(
        buildSectionBlock(`**Context to add:**\n${operation.updateData.descriptionAppend}`)
      );
    }
  }

  // Show related tickets if any
  if (
    triageAnalysis?.relatedTickets &&
    triageAnalysis.relatedTickets.length > 0 &&
    operation?.action !== TaskAction.SKIP
  ) {
    const ticketsList = triageAnalysis.relatedTickets
      .slice(0, 5)
      .map((ticket) => {
        const confidencePercent = Math.round(ticket.confidence * 100);
        const ticketLink = buildLinearUrl(ticket.ticketId, ticket.url);
        return `• [${ticket.ticketId}: ${ticket.title}](${ticketLink}) (${confidencePercent}% match)`;
      })
      .join('\n');

    blocks.push(buildSectionBlock(`**Related tickets found:**\n${ticketsList}`));
  }

  // Post the message
  if (blocks.length > 0) {
    const textFallback = `Triage Quality Debug: ${
      operation?.action === TaskAction.CREATE
        ? 'Would create new issue'
        : operation?.action === TaskAction.UPDATE
          ? 'Would update existing issue'
          : 'Would skip issue creation'
    }`;

    await tenantSlackApp.postMessage({
      channel,
      thread_ts: threadTs,
      text: textFallback,
      blocks,
    });
  }
}

/**
 * Format proactive CREATE message
 * Shows success message with delete button, description, and feedback buttons at bottom
 *
 * @param result - Execution result from Linear operation
 * @returns Slack message blocks
 */
export function formatProactiveCreateMessage(result: ExecutionResult): KnownBlock[] {
  const blocks: KnownBlock[] = [];

  // Extract human-readable ID from URL if available
  const displayId = result.linearIssueUrl
    ? extractLinearIdFromUrl(result.linearIssueUrl) || result.linearIssueIdentifier || ''
    : result.linearIssueIdentifier || '';

  // Get the description from the create operation (raw Linear markdown)
  const description = result.operation.createData?.description || '';

  // 1. Title with link
  blocks.push(
    buildSectionBlock(
      `:white_check_mark: **Created new Linear issue**\n[**${displayId}: ${result.linearIssueTitle}**](${result.linearIssueUrl})`
    )
  );

  // 2. Delete ticket button
  blocks.push({
    type: 'actions',
    block_id: 'triage_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_delete_ticket',
        text: {
          type: 'plain_text',
          text: 'Delete ticket',
          emoji: true,
        },
        value: JSON.stringify({
          linearIssueId: result.linearIssueId,
          linearIssueUrl: result.linearIssueUrl,
        }),
        style: 'danger',
      },
    ],
  });

  // 3. Full ticket description/details
  if (description.trim()) {
    blocks.push(buildSectionBlock(description));
  }

  // 4. Feedback buttons at bottom
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.CREATE,
          action_status: 'executed',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.CREATE,
          action_status: 'executed',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}

/**
 * Format proactive UPDATE message
 * Shows success message with added context and feedback buttons at bottom
 *
 * @param result - Execution result from Linear operation
 * @returns Slack message blocks
 */
export function formatProactiveUpdateMessage(result: ExecutionResult): KnownBlock[] {
  const blocks: KnownBlock[] = [];

  // Extract human-readable ID from URL if available
  const displayId = result.linearIssueUrl
    ? extractLinearIdFromUrl(result.linearIssueUrl) || result.linearIssueIdentifier || ''
    : result.linearIssueIdentifier || '';

  // Get the appended context from the operation
  const descriptionAppend = result.operation.updateData?.descriptionAppend || '';
  const hasContent = descriptionAppend.trim().length > 0;

  // 1. Title with link - different message based on whether content was added
  if (hasContent) {
    blocks.push(
      buildSectionBlock(
        `:white_check_mark: **Context added to existing Linear issue**\n[**${displayId}: ${result.linearIssueTitle}**](${result.linearIssueUrl})`
      )
    );
  } else {
    blocks.push(
      buildSectionBlock(
        `:information_source: **Existing Linear issue found**\n[**${displayId}: ${result.linearIssueTitle}**](${result.linearIssueUrl})\n\nNo new context to add`
      )
    );
  }

  // 2. Added context details (only if content was actually added)
  if (hasContent) {
    blocks.push(buildSectionBlock(`**Added context:**\n${descriptionAppend}`));
  }

  // 3. Feedback buttons at bottom
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.UPDATE,
          action_status: 'executed',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.UPDATE,
          action_status: 'executed',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}

/**
 * Format proactive SKIP message
 * Shows info message with reasoning - no buttons needed
 *
 * @param operation - The Linear operation with skip data
 * @param triageAnalysis - Triage analysis (for finding related ticket info)
 * @returns Slack message blocks
 */
export function formatProactiveSkipMessage(
  operation: LinearOperation,
  triageAnalysis: TriageAnalysis | undefined
): KnownBlock[] {
  const blocks: KnownBlock[] = [];

  if (!operation.skipData) {
    return blocks;
  }

  blocks.push(
    buildSectionBlock(
      `:information_source: **${
        operation.skipData.issueId ? 'Duplicate Linear issue found' : 'No Linear issue created'
      }**`
    )
  );

  if (operation.skipData.issueId) {
    const duplicateIssue = triageAnalysis?.relatedTickets.find(
      (ticket) => ticket.ticketId === operation.skipData?.issueId
    );

    if (duplicateIssue) {
      const confidencePercent = Math.round(duplicateIssue.confidence * 100);
      const ticketLink = buildLinearUrl(duplicateIssue.ticketId, duplicateIssue.url);
      blocks.push(
        buildSectionBlock(
          `[${duplicateIssue.ticketId}: ${duplicateIssue.title}](${ticketLink}) (${confidencePercent}% match)`
        )
      );
    }
  } else if (operation.skipData.reason) {
    blocks.push(buildSectionBlock(operation.skipData.reason));
  }

  // Add feedback buttons
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.SKIP,
          action_status: 'executed',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.SKIP,
          action_status: 'executed',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}

/**
 * Post triage result to Slack thread
 *
 * @param tenantSlackApp - Tenant Slack app instance
 * @param channel - Channel ID
 * @param threadTs - Thread timestamp
 * @param triageAnalysis - Triage analysis from agent
 * @param executionSummary - Summary of operation execution
 */
export async function postTriageResultToSlack(
  tenantSlackApp: TenantSlackApp,
  channel: string,
  threadTs: string,
  triageAnalysis: TriageAnalysis | undefined,
  executionSummary: ExecutionSummary
): Promise<void> {
  const result = executionSummary.results[0];
  if (!result) {
    return;
  }

  let blocks: KnownBlock[] = [];

  // Use appropriate formatter based on action type
  if (result.operation.action === TaskAction.CREATE && result.success) {
    blocks = formatProactiveCreateMessage(result);
  } else if (result.operation.action === TaskAction.UPDATE && result.success) {
    blocks = formatProactiveUpdateMessage(result);
  } else if (result.operation.action === TaskAction.SKIP) {
    blocks = formatProactiveSkipMessage(result.operation, triageAnalysis);
  }

  // Post the message
  if (blocks.length > 0) {
    const textFallback =
      result.operation.action === TaskAction.CREATE
        ? `Created new Linear issue`
        : result.operation.action === TaskAction.UPDATE
          ? `Updated existing Linear issue`
          : `Skipped issue creation`;

    await tenantSlackApp.postMessage({
      channel,
      thread_ts: threadTs,
      text: textFallback,
      blocks,
    });
  }
}

/**
 * Format non-proactive CREATE message
 * Shows triage analysis with "Create ticket" button (button won't execute yet)
 *
 * @param triageAnalysis - Triage analysis from agent
 * @param linearTeamId - Linear team ID for the channel
 * @returns Slack message blocks
 */
export function formatNonProactiveCreateMessage(
  triageAnalysis: TriageAnalysis,
  linearTeamId: string
): KnownBlock[] {
  const blocks: KnownBlock[] = [];
  const operation = triageAnalysis.operation;

  if (operation?.action !== TaskAction.CREATE || !operation.createData) {
    return blocks;
  }

  const { title, description } = operation.createData;

  // 1. Header with analysis
  blocks.push(
    buildSectionBlock(
      ':robot_face: **Triage Analysis: New Issue Detected**\n\n' +
        `I analyzed this message and suggest creating a new Linear ticket`
    )
  );

  // 2. Create ticket button (before title and description)
  blocks.push({
    type: 'actions',
    block_id: 'triage_execute_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_execute_create',
        text: {
          type: 'plain_text',
          text: 'Create ticket',
          emoji: true,
        },
        value: JSON.stringify({
          action: TaskAction.CREATE,
          title,
          linearTeamId,
        }),
        style: 'primary',
      },
    ],
  });

  // 3. Title
  blocks.push(buildSectionBlock(`**Title:** ${title}`));

  // 4. Description (buildSectionBlock will handle markdown conversion)
  if (description?.trim()) {
    const descriptionBlock = buildSectionBlock(`**Description:**\n${description}`);
    // Add block_id for extraction in button handler
    blocks.push({
      ...descriptionBlock,
      block_id: 'triage_description',
    });
  }

  // 5. Feedback buttons at bottom
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.CREATE,
          action_status: 'suggested',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.CREATE,
          action_status: 'suggested',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}

/**
 * Format non-proactive UPDATE message
 * Shows triage analysis with "Update ticket" button (button won't execute yet)
 *
 * @param triageAnalysis - Triage analysis from agent
 * @returns Slack message blocks
 */
export function formatNonProactiveUpdateMessage(triageAnalysis: TriageAnalysis): KnownBlock[] {
  const blocks: KnownBlock[] = [];
  const operation = triageAnalysis.operation;

  if (operation?.action !== TaskAction.UPDATE || !operation.updateData) {
    return blocks;
  }

  const { issueId, descriptionAppend } = operation.updateData;

  // Find the related ticket info
  const relatedTicket = triageAnalysis.relatedTickets.find((t) => t.ticketId === issueId);
  const issueUrl = relatedTicket?.url || buildLinearUrl(issueId);
  const displayId = issueId; // Use issueId directly as display identifier
  const issueTitle = relatedTicket?.title || 'Existing Issue';

  // 1. Header with analysis
  blocks.push(
    buildSectionBlock(
      `:robot_face: **Triage Analysis: Related to Existing Issue**\n\n` +
        `I found this conversation is related to an existing Linear ticket`
    )
  );

  // 2. Update ticket button (before ticket info and context)
  blocks.push({
    type: 'actions',
    block_id: 'triage_execute_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_execute_update',
        text: {
          type: 'plain_text',
          text: 'Update ticket',
          emoji: true,
        },
        value: JSON.stringify({
          action: TaskAction.UPDATE,
          linearIssueId: issueId,
          linearIssueUrl: issueUrl,
        }),
        style: 'primary',
      },
    ],
  });

  // 3. Ticket info
  blocks.push(buildSectionBlock(`[**${displayId}: ${issueTitle}**](${issueUrl})`));

  // 4. Context to add (buildSectionBlock will handle markdown conversion)
  if (descriptionAppend?.trim()) {
    const appendBlock = buildSectionBlock(`**Context to add:**\n${descriptionAppend}`);
    // Add block_id for extraction in button handler
    blocks.push({
      ...appendBlock,
      block_id: 'triage_append_context',
    });
  }

  // 5. Feedback buttons at bottom
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.UPDATE,
          action_status: 'suggested',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.UPDATE,
          action_status: 'suggested',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}

/**
 * Format non-proactive SKIP message
 * Shows that triage ran but determined no action is needed
 *
 * @param triageAnalysis - Triage analysis from agent
 * @returns Slack message blocks
 */
export function formatNonProactiveSkipMessage(triageAnalysis: TriageAnalysis): KnownBlock[] {
  const blocks: KnownBlock[] = [];
  const operation = triageAnalysis.operation;

  if (operation?.action !== TaskAction.SKIP || !operation.skipData) {
    return blocks;
  }

  const { reason } = operation.skipData;

  blocks.push(
    buildSectionBlock(
      `:information_source: **Triage Analysis: No Action Needed**\n\n` +
        `I analyzed this message and determined that no Linear ticket is needed.\n\n` +
        `**Reason:** ${reason || 'The message does not contain actionable information for a ticket.'}`
    )
  );

  // Feedback buttons at bottom
  blocks.push({
    type: 'actions',
    block_id: 'triage_feedback_actions',
    elements: [
      {
        type: 'button',
        action_id: 'triage_feedback_positive',
        text: {
          type: 'plain_text',
          text: '👍 Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.SKIP,
          action_status: 'suggested',
        }),
        style: 'primary',
      },
      {
        type: 'button',
        action_id: 'triage_feedback_negative',
        text: {
          type: 'plain_text',
          text: '👎 Not Helpful',
          emoji: true,
        },
        value: JSON.stringify({
          actionType: TaskAction.SKIP,
          action_status: 'suggested',
        }),
        style: 'danger',
      },
    ],
  });

  return blocks;
}
