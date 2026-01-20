import { BasicEventArgs, MessageEventArgs, SayOptions } from '../types';
import { handleMessage } from './handlers/messageHandler';
import type {
  ChannelCreatedEvent,
  MemberJoinedChannelEvent,
  ReactionAddedEvent,
  ReactionRemovedEvent,
  GenericMessageEvent,
} from '@slack/bolt';
import { onChannelCreated, onChannelJoined, onChannelLeft } from './handlers/channelHandlers';
import { onReactionAdded, onReactionRemoved } from './handlers/reactionHandlers';
import { SlackEvent, MemberLeftChannelEvent } from './schemas';
import { TenantSlackApp } from '../TenantSlackApp';
import { logger } from '../utils/logger';
import { handleError } from '../common';

export interface EventProcessorContext {
  tenantId?: string;
}

export async function processSlackEvent(
  event: SlackEvent,
  tenantSlackApp: TenantSlackApp,
  context: EventProcessorContext = {},
  originalSay?: Function
): Promise<void> {
  logger.info('Processing Slack event', {
    tenantId: context.tenantId,
    eventType: event.type,
    operation: 'event-processing',
  });

  try {
    // Handle different event types and create appropriate args
    switch (event.type) {
      case 'message': {
        // Create MessageEventArgs
        const messageArgs: MessageEventArgs = {
          message: event as GenericMessageEvent, // Cast Zod event to GenericMessageEvent for compatibility
          say: originalSay
            ? async (options: SayOptions) => originalSay(options) // Direct call in Socket Mode
            : async (options: SayOptions) => {
                return tenantSlackApp.postMessage({
                  channel: event.channel,
                  ...options,
                });
              },
          tenantSlackApp,
        };

        logger.debug('Processing message event', {
          tenantId: context.tenantId,
          userId: event.user,
          channelId: event.channel,
          hasText: !!event.text,
          textLength: event.text?.length || 0,
          operation: 'message-event',
        });

        await handleMessage(messageArgs);
        break;
      }

      case 'member_joined_channel': {
        const basicArgs: BasicEventArgs<MemberJoinedChannelEvent> = {
          event: event as MemberJoinedChannelEvent,
          tenantSlackApp,
        };
        await onChannelJoined(basicArgs);
        break;
      }

      case 'member_left_channel': {
        const basicArgs: BasicEventArgs<MemberLeftChannelEvent> = {
          event: event as MemberLeftChannelEvent,
          tenantSlackApp,
        };
        await onChannelLeft(basicArgs);
        break;
      }

      case 'channel_created': {
        const basicArgs: BasicEventArgs<ChannelCreatedEvent> = {
          event: event as ChannelCreatedEvent,
          tenantSlackApp,
        };
        await onChannelCreated(basicArgs);
        break;
      }

      case 'reaction_added': {
        const basicArgs: BasicEventArgs<ReactionAddedEvent> = {
          event: event as ReactionAddedEvent,
          tenantSlackApp,
        };
        await onReactionAdded(basicArgs);
        break;
      }

      case 'reaction_removed': {
        const basicArgs: BasicEventArgs<ReactionRemovedEvent> = {
          event: event as ReactionRemovedEvent,
          tenantSlackApp,
        };
        await onReactionRemoved(basicArgs);
        break;
      }

      default:
        logger.warn('Unhandled event type received', {
          tenantId: context.tenantId,
          eventType: (event as SlackEvent).type,
          operation: 'unhandled-event',
        });
    }

    logger.info('Successfully processed Slack event', {
      tenantId: context.tenantId,
      eventType: event.type,
      operation: 'event-processed',
    });
  } catch (error) {
    handleError('processSlackEvent', error, {
      level: 'error',
      shouldThrow: true,
      tenantId: context.tenantId,
      operation: 'event-processing-error',
      metadata: {
        eventType: event.type,
      },
    });
  }
}
