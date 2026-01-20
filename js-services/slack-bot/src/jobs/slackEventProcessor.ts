import { SQSJobProcessor } from './SQSJobProcessor';
import { z } from 'zod';
import { ExternalSourceSchema } from '@corporate-context/backend-common';
import { SlackEventSchema } from '../events/schemas';
import { processSlackEvent, EventProcessorContext } from '../events/eventProcessor';
import { getTenantSlackAppManager } from '../tenantSlackAppManager';
import { logger } from '../utils/logger';
import { handleError } from '../common';
import { tenantConfigManager } from '../config/tenantConfigManager';
import { getAnalyticsTracker } from '../services/analyticsTracker';
import { joinAllowedChannels } from '../channelJoiner';
import {
  processSampleQuestionAnswerer,
  sendInstallerSuccessNotification,
} from './sampleQuestionAnswerer';
import { config } from '../config';
import { isTenantDeleted } from '../utils/tenantDeletion';
import { onFeedbackButtonClick } from '../events/handlers/buttonHandlers';

// Zod schemas for SQS job messages
// --------------------------------
// WARNING: This must match the pydantic models in Python!
// Be sure to keep these schemas in sync.

// Webhook message from ingestion
const WebhookMessage = z.object({
  tenant_id: z.string(),
  webhook_body: z.string(),
  source_type: z.literal('slack'),
  timestamp: z.string(),
});

// Control message for bot operations
const ControlMessage = z.object({
  tenant_id: z.string(),
  control_type: z.enum([
    'join_all_channels',
    'refresh_bot_credentials',
    'welcome_message',
    'triage_channel_welcome',
  ]),
  source_type: z.literal('control'),
  timestamp: z.string(),
  channel_ids: z.array(z.string()).optional(), // List of channel IDs for triage_channel_welcome
});

const SampleQuestionAnswererMessage = z.object({
  source_type: z.literal('sample_question_answerer'),
  tenant_id: z.string(),
  timestamp: z.string(),
  iteration_count: z.number().optional(),
});

const BackfillNotificationMessage = z.object({
  source_type: z.literal('backfill_notification'),
  tenant_id: z.string(),
  source: ExternalSourceSchema,
});

const BackfillCompleteNotificationMessage = z.object({
  source_type: z.literal('backfill_complete_notification'),
  tenant_id: z.string(),
  source: ExternalSourceSchema,
  backfill_id: z.string(),
});

// Union of all message types the Slack bot can receive
const SlackBotJobMessage = z.discriminatedUnion('source_type', [
  WebhookMessage,
  ControlMessage,
  SampleQuestionAnswererMessage,
  BackfillNotificationMessage,
  BackfillCompleteNotificationMessage,
]);

// Constants
const SAMPLE_QUESTION_ANSWERER_DELAY_MS = 5_000; // 5 second delay between iterations

/**
 * Helper function to send a DM to the installer user
 */
async function sendInstallerDM(
  tenantId: string,
  message: string,
  operation: string
): Promise<void> {
  // Get installer user ID using existing config manager
  const installerUserIdValue = await tenantConfigManager.getConfigValue(
    'SLACK_INSTALLER_USER_ID',
    tenantId
  );
  if (!installerUserIdValue || typeof installerUserIdValue !== 'string') {
    logger.warn('No installer user ID found for tenant', {
      tenantId,
      operation: `${operation}-no-installer`,
    });
    return;
  }

  const installerUserId = installerUserIdValue;

  // Get tenant Slack app to send message
  const appManager = getTenantSlackAppManager();
  const tenantSlackApp = await appManager.getTenantSlackApp(tenantId);

  // Open DM channel with installer (must exist to send DM)
  const dmChannelResponse = await tenantSlackApp.client.conversations.open({
    users: installerUserId,
  });

  if (!dmChannelResponse.channel?.id) {
    logger.error('Failed to open DM channel with installer', {
      tenantId,
      installerUserId,
      operation: `${operation}-dm-channel-failed`,
    });
    return;
  }

  // Send DM to installer
  await tenantSlackApp.postMessage({
    channel: dmChannelResponse.channel.id,
    text: message,
  });

  logger.info('Successfully sent installer DM', {
    tenantId,
    installerUserId,
    operation: `${operation}-sent`,
  });
}

// Webhook message body schema using shared event schemas
// Generally based on @slack/types, with some fields we don't care about excluded
// If you add/remove event types here, you need to add/remove them in the debugIndex.ts for local dev
const SlackEventCallbackBody = z.object({
  type: z.literal('event_callback'),
  team_id: z.string(),
  api_app_id: z.string().optional(),
  event: SlackEventSchema, // Use shared schema from events/schemas.ts
  event_id: z.string(),
  event_time: z.number(),
});

// Block actions body schema for interactive button clicks
const SlackBlockActionsBody = z.object({
  type: z.literal('block_actions'),
  user: z.object({
    id: z.string(),
    username: z.string().optional(),
    name: z.string().optional(),
  }),
  api_app_id: z.string().optional(),
  team: z
    .object({
      id: z.string(),
    })
    .optional(),
  channel: z
    .object({
      id: z.string(),
      name: z.string().optional(),
    })
    .optional(),
  message: z.any().optional(), // The message that contained the button
  container: z.object({
    type: z.string(),
    message_ts: z.string(),
    channel_id: z.string(),
    is_ephemeral: z.boolean().optional(),
  }),
  actions: z.array(z.any()), // Button actions
  trigger_id: z.string().optional(),
});

// Union of event_callback and block_actions
const SlackBotJobMessageBody = z.discriminatedUnion('type', [
  SlackEventCallbackBody,
  SlackBlockActionsBody,
]);

type SlackBotJobMessageType = z.infer<typeof SlackBotJobMessage>;

// --------------------------------

// Process function that routes Slack events from SQS to appropriate handlers
// Takes an optional SQS processor reference for sending messages
async function processSlackJobMessage(
  jobMessage: SlackBotJobMessageType,
  sqsProcessor?: SQSJobProcessor<SlackBotJobMessageType>
): Promise<void> {
  const { tenant_id, source_type } = jobMessage;
  const timestamp = 'timestamp' in jobMessage ? jobMessage.timestamp : undefined;

  // Check if tenant is deleted before processing
  const isDeleted = await isTenantDeleted(tenant_id);
  if (isDeleted) {
    logger.warn(`Skipping slack bot job for deleted tenant ${tenant_id}`, {
      tenantId: tenant_id,
      sourceType: source_type,
      operation: 'skip-deleted-tenant',
    });
    return;
  }

  // Handle control messages
  if (source_type === 'control') {
    const controlMessage = jobMessage as z.infer<typeof ControlMessage>;
    logger.info('Processing control message', {
      tenantId: tenant_id,
      controlType: controlMessage.control_type,
      timestamp,
      operation: 'control-message',
    });

    switch (controlMessage.control_type) {
      case 'join_all_channels': {
        logger.info('Processing join_all_channels control message', {
          tenantId: tenant_id,
          operation: 'join-all-channels',
        });

        try {
          await joinAllowedChannels(tenant_id);

          logger.info('Successfully completed join_all_channels operation', {
            tenantId: tenant_id,
            operation: 'join-all-channels-completed',
          });
        } catch (error) {
          logger.error('Failed to join channels', error, {
            tenantId: tenant_id,
            operation: 'join-all-channels-error',
          });
        }
        return;
      }
      case 'refresh_bot_credentials': {
        const appManager = getTenantSlackAppManager();

        try {
          // Restart the TenantSlackApp to pick up fresh credentials and bot ID
          await appManager.restartTenantSlackApp(tenant_id);
          logger.info('Successfully refreshed bot credentials', {
            tenantId: tenant_id,
            operation: 'credentials-refreshed',
          });
        } catch (error) {
          handleError('refreshBotCredentials', error, {
            level: 'error',
            shouldThrow: true,
            tenantId: tenant_id,
            operation: 'credentials-refresh-error',
          });
        }
        return;
      }
      case 'welcome_message': {
        logger.info('Processing welcome_message control message', {
          tenantId: tenant_id,
          operation: 'welcome-message',
        });

        try {
          const message = `👋 Welcome to Grapevine! I'll automatically index new messages from your public Slack channels from this point on. For better answer quality, I highly recommend you <${config.frontendUrl}|add more data sources and upload a Slack export for historical context> - then I'll show you some examples of how I can help!`;

          await sendInstallerDM(tenant_id, message, 'welcome-message');

          // Track analytics event
          try {
            const installerUserIdValue = await tenantConfigManager.getConfigValue(
              'SLACK_INSTALLER_USER_ID',
              tenant_id
            );
            if (installerUserIdValue && typeof installerUserIdValue === 'string') {
              const analyticsTracker = getAnalyticsTracker();
              await analyticsTracker.trackWelcomeMessageSent(tenant_id, installerUserIdValue);
            }
          } catch (analyticsError) {
            logger.error('Failed to track welcome message analytics', analyticsError, {
              tenantId: tenant_id,
              operation: 'welcome-message-analytics-error',
            });
            // Don't throw - analytics failure shouldn't stop the welcome message
          }
        } catch (error) {
          logger.error('Failed to send welcome message', error, {
            tenantId: tenant_id,
            operation: 'welcome-message-error',
          });
        }
        return;
      }
      case 'triage_channel_welcome': {
        logger.info('Processing triage_channel_welcome control message', {
          tenantId: tenant_id,
          channelCount: controlMessage.channel_ids?.length || 0,
          operation: 'triage-channel-welcome',
        });

        const channelIds = controlMessage.channel_ids || [];
        if (channelIds.length === 0) {
          logger.warn('No channel IDs provided for triage_channel_welcome', {
            tenantId: tenant_id,
            operation: 'triage-channel-welcome-no-channels',
          });
          return;
        }

        try {
          const appManager = getTenantSlackAppManager();
          const tenantSlackApp = await appManager.getTenantSlackApp(tenant_id);

          const message =
            '👋 Triage bot is now active in this channel! All new top-level messages will be automatically triaged and synced to Linear.';

          // Send welcome message to each newly mapped channel
          for (const channelId of channelIds) {
            try {
              await tenantSlackApp.postMessage({
                channel: channelId,
                text: message,
              });

              logger.info('Sent triage welcome message to channel', {
                tenantId: tenant_id,
                channelId,
                operation: 'triage-welcome-sent',
              });
            } catch (error) {
              logger.error('Failed to send triage welcome message to channel', error, {
                tenantId: tenant_id,
                channelId,
                operation: 'triage-welcome-channel-error',
              });
              // Continue with other channels even if one fails
            }
          }

          logger.info('Completed triage channel welcome messages', {
            tenantId: tenant_id,
            totalChannels: channelIds.length,
            operation: 'triage-channel-welcome-completed',
          });
        } catch (error) {
          logger.error('Failed to process triage channel welcome messages', error, {
            tenantId: tenant_id,
            operation: 'triage-channel-welcome-error',
          });
        }
        return;
      }
      default:
        logger.warn('Unknown control message type', {
          tenantId: tenant_id,
          controlType: controlMessage.control_type,
          operation: 'unknown-control-type',
        });
        return;
    }
  }

  // Handle sample question answerer messages
  if (source_type === 'sample_question_answerer') {
    const sampleMessage = jobMessage as z.infer<typeof SampleQuestionAnswererMessage>;
    const iterationCount = sampleMessage.iteration_count || 0;
    const MAX_ITERATIONS = 500;

    logger.info('Processing sample question answerer message', {
      tenantId: tenant_id,
      iterationCount,
      timestamp,
      operation: 'sample-question-answerer',
    });

    // Check max iteration limit
    if (iterationCount >= MAX_ITERATIONS) {
      logger.warn('Sample question answerer reached max iterations - stopping', {
        tenantId: tenant_id,
        iterationCount,
        maxIterations: MAX_ITERATIONS,
        operation: 'sample-question-answerer-max-iterations',
      });
      return;
    }

    // Note: Installer success notification is now sent directly from
    // processSampleQuestionAnswerer when target is reached

    try {
      const result = await processSampleQuestionAnswerer(tenant_id);

      logger.info('Sample question answerer result', {
        tenantId: tenant_id,
        shouldContinue: result.shouldContinue,
        reason: result.reason,
        goodAnswersCount: result.goodAnswersCount,
        iterationCount,
        operation: 'sample-question-answerer-result',
      });

      // If we should continue and haven't reached max iterations, queue another job
      if (result.shouldContinue && iterationCount < MAX_ITERATIONS && sqsProcessor) {
        const nextMessage: z.infer<typeof SampleQuestionAnswererMessage> = {
          source_type: 'sample_question_answerer',
          tenant_id,
          timestamp: new Date().toISOString(),
          iteration_count: iterationCount + 1,
        };

        logger.info('Queueing next sample question answerer iteration', {
          tenantId: tenant_id,
          nextIterationCount: iterationCount + 1,
          delayMs: SAMPLE_QUESTION_ANSWERER_DELAY_MS,
          operation: 'sample-question-answerer-requeue',
        });

        // Add delay before sending next message to reduce system load
        setTimeout(async () => {
          try {
            await sqsProcessor.sendMessage(nextMessage);
          } catch (error) {
            logger.error('Failed to send delayed sample question answerer message', error, {
              tenantId: tenant_id,
              iterationCount: iterationCount + 1,
              operation: 'sample-question-answerer-delayed-send-error',
            });
          }
        }, SAMPLE_QUESTION_ANSWERER_DELAY_MS);
      } else if (result.shouldContinue && !sqsProcessor) {
        logger.warn('Cannot requeue sample question answerer - no SQS processor available', {
          tenantId: tenant_id,
          iterationCount,
          operation: 'sample-question-answerer-no-processor',
        });
      } else if (!result.shouldContinue && result.reason === 'max_answers_reached') {
        logger.info(
          'Sample question answerer reached max answers - sending installer notification',
          {
            tenantId: tenant_id,
            goodAnswersCount: result.goodAnswersCount,
            operation: 'sample-question-answerer-max-answers-reached',
          }
        );

        // Send installer notification using the tenant Slack app
        try {
          const tenantSlackAppManager = getTenantSlackAppManager();
          const tenantSlackApp = await tenantSlackAppManager.getTenantSlackApp(tenant_id);

          if (tenantSlackApp) {
            await sendInstallerSuccessNotification(tenant_id, tenantSlackApp);

            logger.info('Successfully sent installer success notification from SQS processor', {
              tenantId: tenant_id,
              operation: 'sample-question-answerer-installer-notification-sent',
            });
          } else {
            logger.warn('No TenantSlackApp available for installer notification', {
              tenantId: tenant_id,
              operation: 'sample-question-answerer-no-slack-app',
            });
          }
        } catch (notificationError) {
          logger.error(
            'Failed to send installer notification from SQS processor',
            notificationError,
            {
              tenantId: tenant_id,
              operation: 'sample-question-answerer-installer-notification-error',
            }
          );
          // Don't throw - this shouldn't stop the main flow
        }
      }
    } catch (error) {
      handleError('processSampleQuestionAnswerer', error, {
        level: 'error',
        shouldThrow: true,
        tenantId: tenant_id,
        operation: 'sample-question-answerer-error',
      });
    }

    return;
  }

  // Handle backfill start notification messages
  if (source_type === 'backfill_notification') {
    const notificationMessage = jobMessage as z.infer<typeof BackfillNotificationMessage>;
    const source = notificationMessage.source;
    logger.info('Processing backfill notification message', {
      tenantId: tenant_id,
      source,
      operation: 'backfill-notification',
    });

    try {
      // Create source-specific message
      const sourceMessages: Record<z.infer<typeof ExternalSourceSchema>, string> = {
        linear:
          'Linear issues! Note that Linear has strict API rate limits, so this may take a while (days, for big workspaces).',
        github: 'GitHub pull requests and files!',
        notion:
          'Notion pages! Note that Notion has strict API rate limits, so this may take a while (hours, or even days).',
        google_drive: 'Google Drive files!',
        google_email: 'Google Email messages!',
        slack: 'Slack messages!',
        salesforce: 'Salesforce records!',
        hubspot: 'HubSpot data!',
        jira: 'Jira data!',
        gong: 'Gong data!',
        gather: 'Gather meeting data!',
        zendesk: 'Zendesk tickets!',
        trello: 'Trello boards and cards!',
        asana: 'Asana tasks!',
        attio: 'Attio CRM data!',
        intercom: 'Intercom conversations and articles!',
        fireflies: 'Fireflies meeting transcripts!',
        gitlab: 'GitLab merge requests and code!',
        pylon: 'Pylon support issues!',
        monday: 'Monday.com boards and items!',
        pipedrive: 'Pipedrive deals and contacts!',
        clickup: 'ClickUp tasks and comments!',
        figma: 'Figma design files and comments!',
        posthog: 'PostHog dashboards and insights!',
        canva: 'Canva design files!',
        teamwork: 'Teamwork tasks!',
        custom_data: 'Custom data documents!',
      };

      const message = `🔄 Grapevine is now indexing your ${sourceMessages[source]} I'll notify you when the import is complete, but in the meantime keep in mind that not all your data may be available yet.`;

      await sendInstallerDM(tenant_id, message, 'backfill-notification');
    } catch (error) {
      logger.error('Failed to send backfill notification', error, {
        tenantId: tenant_id,
        source,
        operation: 'backfill-notification-error',
      });
      throw error;
    }

    return;
  }

  // Handle backfill complete notification messages
  if (source_type === 'backfill_complete_notification') {
    const notificationMessage = jobMessage as z.infer<typeof BackfillCompleteNotificationMessage>;
    const { source, backfill_id } = notificationMessage;
    logger.info('Processing backfill complete notification message', {
      tenantId: tenant_id,
      source,
      backfill_id,
      operation: 'backfill-complete-notification',
    });

    try {
      // Create source-specific message
      const sourceNames: Record<z.infer<typeof ExternalSourceSchema>, string> = {
        linear: 'Linear',
        github: 'GitHub',
        notion: 'Notion',
        google_drive: 'Google Drive',
        google_email: 'Google Email',
        slack: 'Slack',
        salesforce: 'Salesforce',
        hubspot: 'HubSpot',
        jira: 'Jira',
        gong: 'Gong',
        gather: 'Gather',
        zendesk: 'Zendesk',
        trello: 'Trello',
        asana: 'Asana',
        attio: 'Attio',
        intercom: 'Intercom',
        fireflies: 'Fireflies',
        gitlab: 'GitLab',
        pylon: 'Pylon',
        monday: 'Monday.com',
        pipedrive: 'Pipedrive',
        clickup: 'ClickUp',
        figma: 'Figma',
        posthog: 'PostHog',
        canva: 'Canva',
        teamwork: 'Teamwork',
        custom_data: 'Custom Data',
      };

      const message = `✅ Your ${sourceNames[source]} import is complete! You can try asking me a question related to your ${sourceNames[source]} data by replying here or tagging me in any channel.`;

      await sendInstallerDM(tenant_id, message, 'backfill-complete');
    } catch (error) {
      logger.error('Failed to send backfill complete notification', error, {
        tenantId: tenant_id,
        source,
        backfill_id,
        operation: 'backfill-complete-notification-error',
      });
      throw error;
    }

    return;
  }

  // Handle webhook messages (existing logic)
  const webhookMessage = jobMessage as z.infer<typeof WebhookMessage>;
  const { webhook_body } = webhookMessage;
  const parsedWebhookBody = SlackBotJobMessageBody.parse(JSON.parse(webhook_body));

  // Get tenant-specific Slack app
  const appManager = getTenantSlackAppManager();
  const tenantSlackApp = await appManager.getTenantSlackApp(tenant_id);

  try {
    // Check if this is a block_actions payload
    if (parsedWebhookBody.type === 'block_actions') {
      // Handle block actions (button clicks)
      const blockActionsPayload = parsedWebhookBody;

      logger.info('Processing block_actions from SQS', {
        tenantId: tenant_id,
        userId: blockActionsPayload.user.id,
        actionCount: blockActionsPayload.actions.length,
        operation: 'block-actions-processing',
      });

      // Convert to BlockActionEvent format expected by the handler
      const blockActionEvent = {
        type: 'block_actions' as const,
        user: blockActionsPayload.user,
        actions: blockActionsPayload.actions,
        channel: blockActionsPayload.channel,
        message: blockActionsPayload.message,
        container: blockActionsPayload.container,
      };

      // Check action_id to route to appropriate handler
      const action = blockActionsPayload.actions[0];
      const actionId = action && 'action_id' in action ? action.action_id : undefined;

      if (actionId && ['triage_delete_ticket', 'triage_undo_update'].includes(actionId)) {
        // Route to triage button handler
        const { onTriageButtonClick } = await import('../events/handlers/triageButtonHandlers');
        await onTriageButtonClick({
          event: blockActionEvent,
          tenantSlackApp,
        });
      } else if (
        actionId &&
        ['triage_execute_create', 'triage_execute_update'].includes(actionId)
      ) {
        // Route to non-proactive triage button handler
        const { onNonProactiveTriageButtonClick } = await import(
          '../events/handlers/triageButtonHandlers'
        );
        await onNonProactiveTriageButtonClick({
          event: blockActionEvent,
          tenantSlackApp,
        });
      } else if (
        actionId &&
        ['triage_feedback_positive', 'triage_feedback_negative'].includes(actionId)
      ) {
        // Route to triage feedback button handler
        const { onTriageFeedbackButtonClick } = await import(
          '../events/handlers/triageButtonHandlers'
        );
        await onTriageFeedbackButtonClick({
          event: blockActionEvent,
          tenantSlackApp,
        });
      } else if (actionId && ['feedback_positive', 'feedback_negative'].includes(actionId)) {
        // Route to feedback button handler
        await onFeedbackButtonClick({
          event: blockActionEvent,
          tenantSlackApp,
        });
      } else {
        logger.warn('Unknown action_id in block_actions', {
          tenantId: tenant_id,
          actionId,
          operation: 'unknown-action-id',
        });
      }

      logger.info('Successfully processed block_actions from SQS', {
        tenantId: tenant_id,
        actionId,
        operation: 'block-actions-processed',
      });
    } else {
      // Handle event_callback (existing logic)
      const { event } = parsedWebhookBody;

      // Create event processor context
      const context: EventProcessorContext = {
        tenantId: tenant_id,
      };

      // Call processSlackEvent directly - it handles all the switch logic and args construction
      await processSlackEvent(event, tenantSlackApp, context);
    }
  } catch (error) {
    handleError('processSlackJobMessage', error, {
      level: 'error',
      shouldThrow: true,
      tenantId: tenant_id,
      operation: 'slack-event-processing-error',
      metadata: {
        payloadType: parsedWebhookBody.type,
      },
    });
  }
}

// Create and export a configured SQS job processor for Slack events
export function createSlackEventProcessor(
  queueArn: string
): SQSJobProcessor<SlackBotJobMessageType> {
  // Allow configuration via environment variable, default to 20
  const maxConcurrency = process.env.SLACK_BOT_MAX_CONCURRENCY
    ? parseInt(process.env.SLACK_BOT_MAX_CONCURRENCY, 10)
    : 20;

  return new SQSJobProcessor({
    queueArn,
    schema: SlackBotJobMessage,
    processFunction: processSlackJobMessage,
    maxMessages: 5, // Fetch up to 5 messages per poll
    waitTimeSeconds: 20, // Long polling
    // give ask_agent plenty of time to complete to minimize duplicate answers
    visibilityTimeoutSeconds: 600, // 10 mins
    maxConcurrency, // Process up to this many messages concurrently
  });
}

export default createSlackEventProcessor;
