/**
 * Debug Index - Single-Tenant Slack App for Local Development
 *
 * This file contains the single-tenant Slack app initialization code that was
 * originally in index.ts. It's preserved here for local debugging purposes.
 *
 * Usage:
 * - Set DEBUG_MODE=true environment variable to use this mode
 * - Requires hardcoded tokens in config/env vars (SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, etc.)
 * - Optionally uses Socket Mode for real-time event handling (if SLACK_APP_TOKEN is provided)
 * - All events are handled directly by this single app instance
 *
 * In production, the multi-tenant architecture processes events from SQS
 * and dynamically instantiates Slack apps per tenant using SSM secrets.
 */

import { TenantSlackApp } from './TenantSlackApp';
import { SlackEventSchema } from './events/schemas';
import { processSlackEvent, EventProcessorContext } from './events/eventProcessor';
import { logger } from './utils/logger';

// Note: withTenantContext wrapper removed - tenant ID is set once at startup for debug mode

// This debug version uses socket mode and hence has listeners for each event type
// If you want to add and remove event listeners, you need to add/remove them here
// and in the types in slackEventProcessor, and in the config for the prod Slack app
export async function startDebugSlackApp() {
  logger.info('Starting debug Slack app...', { operation: 'debug-start' });

  // Create real TenantSlackApp for debug mode
  const debugTenantId = process.env.DEBUG_TENANT_ID || 'debug-tenant';
  const debugTenantApp = await TenantSlackApp.createForDebug(debugTenantId);

  // Set tenant ID once for the entire debug session - no need to set/clear per event
  logger.error(
    'Removed tenant resolver because it was fundamentally broken. If you use debugIndex, please figure out how to handle tenant id correctly.'
  );
  // setCurrentTenantId(debugTenantId);
  logger.info(`Set persistent tenant ID for debug mode: ${debugTenantId}`, {
    tenantId: debugTenantId,
    operation: 'debug-setup',
  });

  // Get the app instance for event handlers
  const app = debugTenantApp.app;

  // Simple event processor for all event types
  const processUnifiedEvent = async (
    eventType: string,
    eventData: unknown,
    originalSay?: Function
  ) => {
    try {
      // Validate event with Zod schema
      const validatedEvent = SlackEventSchema.parse({
        type: eventType,
        ...(typeof eventData === 'object' && eventData !== null ? eventData : {}),
      });

      // Create event processor context
      const context: EventProcessorContext = {
        tenantId: debugTenantId,
      };

      // Call processSlackEvent directly - it handles all the switch logic and args construction
      await processSlackEvent(validatedEvent, debugTenantApp, context, originalSay);
    } catch (error) {
      logger.error(
        `Error processing ${eventType} event`,
        error instanceof Error ? error : new Error(String(error)),
        { eventType, tenantId: debugTenantId, operation: 'event-processing' }
      );
      throw error;
    }
  };

  // Register unified handlers for all event types - no tenant context wrapper needed in debug mode
  app.message(async (args) => {
    await processUnifiedEvent('message', args.message, args.say);
  });

  app.event('channel_created', async (args) => {
    await processUnifiedEvent('channel_created', args.event);
  });

  app.event('member_joined_channel', async (args) => {
    await processUnifiedEvent('member_joined_channel', args.event);
  });

  app.event('reaction_added', async (args) => {
    await processUnifiedEvent('reaction_added', args.event);
  });

  app.event('reaction_removed', async (args) => {
    await processUnifiedEvent('reaction_removed', args.event);
  });

  // Button action handlers for feedback and triage buttons
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleButtonAction = async ({ body, ack, action }: any) => {
    logger.info('🔘 Button action received!', {
      actionId: action.action_id,
      operation: 'button-action-received',
    });

    await ack();
    logger.info('✅ Button action acknowledged', { operation: 'button-action-acked' });

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const blockActionsBody = body as any;

      // Convert to BlockActionEvent format
      const blockActionEvent = {
        type: 'block_actions' as const,
        user: blockActionsBody.user,
        actions: blockActionsBody.actions,
        channel: blockActionsBody.channel,
        message: blockActionsBody.message,
        container: blockActionsBody.container,
      };

      // Route to appropriate handler based on action_id
      const actionId = action.action_id;
      if (['triage_delete_ticket', 'triage_undo_update'].includes(actionId)) {
        // Handle triage actions
        const { onTriageButtonClick } = await import('./events/handlers/triageButtonHandlers');
        await onTriageButtonClick({
          event: blockActionEvent,
          tenantSlackApp: debugTenantApp,
        });
      } else if (['feedback_positive', 'feedback_negative'].includes(actionId)) {
        // Handle feedback actions
        const { onFeedbackButtonClick } = await import('./events/handlers/buttonHandlers');
        await onFeedbackButtonClick({
          event: blockActionEvent,
          tenantSlackApp: debugTenantApp,
        });
      }

      logger.info('✅ Button handler completed', { operation: 'button-handler-completed' });
    } catch (error) {
      logger.error(
        '❌ Button handler error',
        error instanceof Error ? error : new Error(String(error)),
        {
          operation: 'button-handler-error',
        }
      );
    }
  };

  // Register feedback button actions
  app.action('feedback_positive', handleButtonAction);
  app.action('feedback_negative', handleButtonAction);

  // Register triage button actions
  app.action('triage_delete_ticket', handleButtonAction);
  app.action('triage_undo_update', handleButtonAction);

  // Catch-all action handler for debugging
  app.action(/.+/, async ({ action, ack }) => {
    logger.info('🔍 ANY action received (catch-all)', {
      actionId: 'action_id' in action ? action.action_id : undefined,
      actionType: 'type' in action ? action.type : undefined,
      action: JSON.stringify(action),
      operation: 'catch-all-action',
    });
    await ack();
  });

  process.on('uncaughtException', (error) => {
    logger.error('Uncaught Exception', error instanceof Error ? error : new Error(String(error)), {
      operation: 'uncaught-exception',
    });
  });

  process.on('unhandledRejection', (reason) => {
    logger.error(
      'Unhandled Rejection',
      reason instanceof Error ? reason : new Error(String(reason)),
      {
        operation: 'unhandled-rejection',
      }
    );
  });

  // stop app gracefully when control + c is pressed
  async function stopApp() {
    logger.info('⚡️ Debug Slack app is stopping!', { operation: 'debug-shutdown' });
    await app.stop();
    process.exit();
  }

  process.on('SIGINT', stopApp);
  process.on('SIGTERM', stopApp);

  // Start the app (already initialized by TenantSlackApp.createForDebug)
  await app.start();

  logger.info('Debug Slack app running!', {
    tenantId: debugTenantId,
    botId: debugTenantApp.botId,
    port: process.env.PORT || '8000',
    operation: 'debug-ready',
  });

  return app;
}
