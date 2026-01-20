/**
 * Slack Messages Data Access Layer (DAL)
 *
 * Handles all database operations related to slack_messages table
 * These are tenant database operations, not control database
 */

import { Pool } from 'pg';
import { createLogger } from '../logger';

const logger = createLogger('slack-messages-dal');

export interface SlackMessage {
  message_id: string;
  channel_id: string;
  user_id: string;
  question: string;
  answer: string;
  bot_response_message_id: string | null;
  model_response_id: string | null;
  created_at: Date;
}

/**
 * Get the model response ID for a specific Slack message
 * Used for conversation continuation in threaded responses
 *
 * @param db - Database connection pool (tenant-specific)
 * @param channelId - Slack channel ID
 * @param messageId - Slack message timestamp (unique identifier)
 * @returns The model response ID, or null if not found
 */
export async function getModelResponseId(
  db: Pool,
  channelId: string,
  messageId: string
): Promise<string | null> {
  try {
    const query = `
      SELECT model_response_id
      FROM public.slack_messages
      WHERE channel_id = $1 AND message_id = $2
      LIMIT 1
    `;

    const result = await db.query(query, [channelId, messageId]);

    if (result.rows.length === 0) {
      logger.info('No slack message found for given channel and message ID', {
        channelId,
        messageId,
        operation: 'get-model-response-id',
      });
      return null;
    }

    const modelResponseId = result.rows[0]?.model_response_id || null;

    logger.info('Retrieved model response ID', {
      channelId,
      messageId,
      hasResponseId: !!modelResponseId,
      operation: 'get-model-response-id',
    });

    return modelResponseId;
  } catch (error) {
    logger.error('Error retrieving model response ID', {
      error: error instanceof Error ? error.message : 'Unknown error',
      channelId,
      messageId,
      operation: 'get-model-response-id',
    });
    throw error;
  }
}

/**
 * Get the model response ID by bot's response message timestamp
 * Used when looking up the response ID from a bot's message in a thread
 *
 * @param db - Database connection pool (tenant-specific)
 * @param botResponseMessageId - Slack timestamp of the bot's response message
 * @returns The model response ID, or null if not found
 */
export async function getModelResponseIdByBotMessageId(
  db: Pool,
  botResponseMessageId: string
): Promise<string | null> {
  try {
    const query = `
      SELECT model_response_id
      FROM public.slack_messages
      WHERE bot_response_message_id = $1
      ORDER BY created_at DESC
      LIMIT 1
    `;

    const result = await db.query(query, [botResponseMessageId]);

    if (result.rows.length === 0) {
      logger.info('No slack message found for given bot response message ID', {
        botResponseMessageId,
        operation: 'get-model-response-id-by-bot-message',
      });
      return null;
    }

    const modelResponseId = result.rows[0]?.model_response_id || null;

    logger.info('Retrieved model response ID by bot message ID', {
      botResponseMessageId,
      hasResponseId: !!modelResponseId,
      operation: 'get-model-response-id-by-bot-message',
      responseId: modelResponseId,
    });

    return modelResponseId;
  } catch (error) {
    logger.error('Error retrieving model response ID by bot message ID', {
      error: error instanceof Error ? error.message : 'Unknown error',
      botResponseMessageId,
      operation: 'get-model-response-id-by-bot-message',
    });
    throw error;
  }
}

/**
 * Get a complete slack message record by channel and message ID
 *
 * @param db - Database connection pool (tenant-specific)
 * @param channelId - Slack channel ID
 * @param messageId - Slack message timestamp (unique identifier)
 * @returns The complete slack message record, or null if not found
 */
export async function getSlackMessage(
  db: Pool,
  channelId: string,
  messageId: string
): Promise<SlackMessage | null> {
  try {
    const query = `
      SELECT
        message_id,
        channel_id,
        user_id,
        question,
        answer,
        bot_response_message_id,
        model_response_id,
        created_at
      FROM public.slack_messages
      WHERE channel_id = $1 AND message_id = $2
      LIMIT 1
    `;

    const result = await db.query(query, [channelId, messageId]);

    if (result.rows.length === 0) {
      logger.info('No slack message found for given channel and message ID', {
        channelId,
        messageId,
        operation: 'get-slack-message',
      });
      return null;
    }

    const row = result.rows[0];
    const message: SlackMessage = {
      message_id: row.message_id,
      channel_id: row.channel_id,
      user_id: row.user_id,
      question: row.question,
      answer: row.answer,
      bot_response_message_id: row.bot_response_message_id,
      model_response_id: row.model_response_id,
      created_at: row.created_at,
    };

    logger.info('Retrieved slack message', {
      channelId,
      messageId,
      hasResponseId: !!message.model_response_id,
      operation: 'get-slack-message',
    });

    return message;
  } catch (error) {
    logger.error('Error retrieving slack message', {
      error: error instanceof Error ? error.message : 'Unknown error',
      channelId,
      messageId,
      operation: 'get-slack-message',
    });
    throw error;
  }
}
