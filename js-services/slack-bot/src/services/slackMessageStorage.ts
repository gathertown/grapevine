/**
 * Slack Message Storage Service
 *
 * Handles storing and retrieving Slack bot Q&A interactions and user reactions
 * in tenant-specific PostgreSQL databases.
 */

import { logger } from '../utils/logger';
import { tenantDbConnectionManager } from '../config/tenantDbConnectionManager';
import { SlackMessagesDAL } from '@corporate-context/backend-common';

export interface SlackMessageData {
  messageId: string; // Slack message timestamp (unique identifier)
  channelId: string; // Slack channel ID
  userId: string; // Slack user ID who asked the question
  question: string; // Original question text
  answer: string; // Bot's response
  threadTs?: string; // Thread timestamp if in a thread
  responseId?: string; // Backend response ID for conversation continuation
  responseTimeMs?: number; // Time taken to generate response
  botResponseMessageId?: string; // Bot's response message timestamp (for reaction tracking)
  isProactive?: boolean; // Whether this was a proactive response (not a DM/mention)
}

export interface SlackReactionData {
  messageId: string; // References the slack message timestamp
  channelId: string; // Slack channel ID
  userId: string; // User who reacted
  reaction: string; // Reaction type (+1, -1, thumbsup, thumbsdown)
}

export interface SlackFeedbackData {
  messageId: string; // Bot's response message timestamp
  channelId: string; // Slack channel ID
  userId: string; // User who provided feedback
  feedbackType: 'positive' | 'negative'; // Feedback type from button
}

/**
 * Service class for managing Slack message storage in tenant-specific databases
 */
export class SlackMessageStorage {
  /**
   * Validate Slack message data before database operations
   */
  private validateSlackMessageData(data: SlackMessageData): void {
    if (!data.messageId || typeof data.messageId !== 'string' || data.messageId.trim() === '') {
      throw new Error('Invalid messageId: must be a non-empty string');
    }

    if (!data.channelId || typeof data.channelId !== 'string' || data.channelId.trim() === '') {
      throw new Error('Invalid channelId: must be a non-empty string');
    }

    if (!data.userId || typeof data.userId !== 'string' || data.userId.trim() === '') {
      throw new Error('Invalid userId: must be a non-empty string');
    }

    if (!data.question || typeof data.question !== 'string' || data.question.trim() === '') {
      throw new Error('Invalid question: must be a non-empty string');
    }

    if (!data.answer || typeof data.answer !== 'string' || data.answer.trim() === '') {
      throw new Error('Invalid answer: must be a non-empty string');
    }

    // Optional fields validation
    if (
      data.threadTs !== undefined &&
      (typeof data.threadTs !== 'string' || data.threadTs.trim() === '')
    ) {
      throw new Error('Invalid threadTs: must be a non-empty string or undefined');
    }

    if (
      data.responseId !== undefined &&
      (typeof data.responseId !== 'string' || data.responseId.trim() === '')
    ) {
      throw new Error('Invalid responseId: must be a non-empty string or undefined');
    }

    if (
      data.responseTimeMs !== undefined &&
      (typeof data.responseTimeMs !== 'number' || data.responseTimeMs < 0)
    ) {
      throw new Error('Invalid responseTimeMs: must be a non-negative number or undefined');
    }

    if (
      data.botResponseMessageId !== undefined &&
      (typeof data.botResponseMessageId !== 'string' || data.botResponseMessageId.trim() === '')
    ) {
      throw new Error('Invalid botResponseMessageId: must be a non-empty string or undefined');
    }

    // Slack ID format validation (basic patterns)
    if (!this.isValidSlackTimestamp(data.messageId)) {
      throw new Error('Invalid messageId format: must be a valid Slack timestamp');
    }

    if (!this.isValidSlackChannelId(data.channelId)) {
      throw new Error(
        'Invalid channelId format: must start with C or D followed by alphanumeric characters'
      );
    }

    if (!this.isValidSlackUserId(data.userId)) {
      throw new Error(
        'Invalid userId format: must start with U followed by alphanumeric characters'
      );
    }

    if (data.botResponseMessageId && !this.isValidSlackTimestamp(data.botResponseMessageId)) {
      throw new Error('Invalid botResponseMessageId format: must be a valid Slack timestamp');
    }
  }

  /**
   * Validate Slack reaction data before database operations
   */
  private validateSlackReactionData(data: SlackReactionData): void {
    if (!data.messageId || typeof data.messageId !== 'string' || data.messageId.trim() === '') {
      throw new Error('Invalid messageId: must be a non-empty string');
    }

    if (!data.channelId || typeof data.channelId !== 'string' || data.channelId.trim() === '') {
      throw new Error('Invalid channelId: must be a non-empty string');
    }

    if (!data.userId || typeof data.userId !== 'string' || data.userId.trim() === '') {
      throw new Error('Invalid userId: must be a non-empty string');
    }

    if (!data.reaction || typeof data.reaction !== 'string' || data.reaction.trim() === '') {
      throw new Error('Invalid reaction: must be a non-empty string');
    }

    // Format validation
    if (!this.isValidSlackTimestamp(data.messageId)) {
      throw new Error('Invalid messageId format: must be a valid Slack timestamp');
    }

    if (!this.isValidSlackChannelId(data.channelId)) {
      throw new Error(
        'Invalid channelId format: must start with C or D followed by alphanumeric characters'
      );
    }

    if (!this.isValidSlackUserId(data.userId)) {
      throw new Error(
        'Invalid userId format: must start with U followed by alphanumeric characters'
      );
    }
  }

  /**
   * Validate reaction removal data (without channelId requirement)
   */
  private validateReactionRemovalData(messageId: string, userId: string, reaction: string): void {
    if (!messageId || typeof messageId !== 'string' || messageId.trim() === '') {
      throw new Error('Invalid messageId: must be a non-empty string');
    }

    if (!userId || typeof userId !== 'string' || userId.trim() === '') {
      throw new Error('Invalid userId: must be a non-empty string');
    }

    if (!reaction || typeof reaction !== 'string' || reaction.trim() === '') {
      throw new Error('Invalid reaction: must be a non-empty string');
    }

    // Format validation
    if (!this.isValidSlackTimestamp(messageId)) {
      throw new Error('Invalid messageId format: must be a valid Slack timestamp');
    }

    if (!this.isValidSlackUserId(userId)) {
      throw new Error(
        'Invalid userId format: must start with U followed by alphanumeric characters'
      );
    }
  }

  /**
   * Validate button feedback data before database operations
   */
  private validateSlackFeedbackData(data: SlackFeedbackData): void {
    if (!data.messageId || typeof data.messageId !== 'string' || data.messageId.trim() === '') {
      throw new Error('Invalid messageId: must be a non-empty string');
    }

    if (!data.channelId || typeof data.channelId !== 'string' || data.channelId.trim() === '') {
      throw new Error('Invalid channelId: must be a non-empty string');
    }

    if (!data.userId || typeof data.userId !== 'string' || data.userId.trim() === '') {
      throw new Error('Invalid userId: must be a non-empty string');
    }

    if (!data.feedbackType || !['positive', 'negative'].includes(data.feedbackType)) {
      throw new Error('Invalid feedbackType: must be "positive" or "negative"');
    }

    // Format validation
    if (!this.isValidSlackTimestamp(data.messageId)) {
      throw new Error('Invalid messageId format: must be a valid Slack timestamp');
    }

    if (!this.isValidSlackChannelId(data.channelId)) {
      throw new Error(
        'Invalid channelId format: must start with C or D followed by alphanumeric characters'
      );
    }

    if (!this.isValidSlackUserId(data.userId)) {
      throw new Error(
        'Invalid userId format: must start with U followed by alphanumeric characters'
      );
    }
  }

  /**
   * Validate feedback removal data (without channelId requirement)
   */
  private validateFeedbackRemovalData(messageId: string, userId: string): void {
    if (!messageId || typeof messageId !== 'string' || messageId.trim() === '') {
      throw new Error('Invalid messageId: must be a non-empty string');
    }

    if (!userId || typeof userId !== 'string' || userId.trim() === '') {
      throw new Error('Invalid userId: must be a non-empty string');
    }

    // Format validation
    if (!this.isValidSlackTimestamp(messageId)) {
      throw new Error('Invalid messageId format: must be a valid Slack timestamp');
    }

    if (!this.isValidSlackUserId(userId)) {
      throw new Error(
        'Invalid userId format: must start with U followed by alphanumeric characters'
      );
    }
  }

  /**
   * Validate tenant ID format
   */
  private validateTenantId(tenantId: string): void {
    if (!tenantId || typeof tenantId !== 'string' || tenantId.trim() === '') {
      throw new Error('Invalid tenantId: must be a non-empty string');
    }
  }

  /**
   * Check if a string is a valid Slack timestamp format
   */
  private isValidSlackTimestamp(timestamp: string): boolean {
    // Slack timestamps are in format: 1234567890.123456 (Unix timestamp with microseconds)
    return /^\d{10}\.\d{6}$/.test(timestamp);
  }

  /**
   * Check if a string is a valid Slack channel ID format
   */
  private isValidSlackChannelId(channelId: string): boolean {
    // Channel IDs start with C (public) or D (DM) followed by uppercase alphanumeric
    return /^[CD][0-9A-Z]{8,}$/.test(channelId);
  }

  /**
   * Check if a string is a valid Slack user ID format
   */
  private isValidSlackUserId(userId: string): boolean {
    // User IDs start with U followed by uppercase alphanumeric
    return /^U[0-9A-Z]{8,}$/.test(userId);
  }

  /**
   * Store a Q&A interaction in the tenant's database
   */
  async storeMessage(tenantId: string, messageData: SlackMessageData): Promise<boolean> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);
      this.validateSlackMessageData(messageData);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'store-message',
        });
        return false;
      }

      const query = `
        INSERT INTO public.slack_messages (
          message_id, channel_id, user_id, question, answer, bot_response_message_id, model_response_id, is_proactive, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        ON CONFLICT (message_id) DO UPDATE SET
          answer = EXCLUDED.answer,
          bot_response_message_id = EXCLUDED.bot_response_message_id,
          model_response_id = EXCLUDED.model_response_id,
          is_proactive = EXCLUDED.is_proactive,
          created_at = CURRENT_TIMESTAMP
      `;

      const values = [
        messageData.messageId,
        messageData.channelId,
        messageData.userId,
        messageData.question,
        messageData.answer,
        messageData.botResponseMessageId || null,
        messageData.responseId || null,
        messageData.isProactive ?? false,
      ];

      await pool.query(query, values);

      logger.info('Successfully stored Slack message', {
        tenantId,
        messageId: messageData.messageId,
        channelId: messageData.channelId,
        userId: messageData.userId,
        hasThreadTs: !!messageData.threadTs,
        hasResponseId: !!messageData.responseId,
        responseTimeMs: messageData.responseTimeMs,
        operation: 'store-message',
      });

      return true;
    } catch (error) {
      logger.error(
        'Failed to store Slack message',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          messageId: messageData.messageId,
          channelId: messageData.channelId,
          userId: messageData.userId,
          operation: 'store-message',
        }
      );
      return false;
    }
  }

  /**
   * Store a user reaction to a bot message
   */
  async storeReaction(tenantId: string, reactionData: SlackReactionData): Promise<boolean> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);
      this.validateSlackReactionData(reactionData);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'store-reaction',
        });
        return false;
      }

      const query = `
        INSERT INTO public.slack_message_reactions (
          message_id, channel_id, user_id, reaction, created_at
        ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        ON CONFLICT (message_id, user_id, reaction) DO NOTHING
      `;

      const values = [
        reactionData.messageId,
        reactionData.channelId,
        reactionData.userId,
        reactionData.reaction,
      ];

      const result = await pool.query(query, values);

      logger.info('Successfully stored Slack reaction', {
        tenantId,
        messageId: reactionData.messageId,
        channelId: reactionData.channelId,
        userId: reactionData.userId,
        reaction: reactionData.reaction,
        wasInserted: result.rowCount === 1,
        operation: 'store-reaction',
      });

      return true;
    } catch (error) {
      logger.error(
        'Failed to store Slack reaction',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          messageId: reactionData.messageId,
          channelId: reactionData.channelId,
          userId: reactionData.userId,
          reaction: reactionData.reaction,
          operation: 'store-reaction',
        }
      );
      return false;
    }
  }

  /**
   * Remove a user reaction from a bot message
   */
  async removeReaction(
    tenantId: string,
    messageId: string,
    userId: string,
    reaction: string
  ): Promise<boolean> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);
      this.validateReactionRemovalData(messageId, userId, reaction);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'remove-reaction',
        });
        return false;
      }

      const query = `
        DELETE FROM public.slack_message_reactions
        WHERE message_id = $1 AND user_id = $2 AND reaction = $3
      `;

      const values = [messageId, userId, reaction];
      const result = await pool.query(query, values);

      logger.info('Successfully removed Slack reaction', {
        tenantId,
        messageId,
        userId,
        reaction,
        wasDeleted: result.rowCount === 1,
        operation: 'remove-reaction',
      });

      return true;
    } catch (error) {
      logger.error(
        'Failed to remove Slack reaction',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          messageId,
          userId,
          reaction,
          operation: 'remove-reaction',
        }
      );
      return false;
    }
  }

  /**
   * Store user feedback from interactive button
   */
  async storeFeedback(tenantId: string, feedbackData: SlackFeedbackData): Promise<boolean> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);
      this.validateSlackFeedbackData(feedbackData);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'store-feedback',
        });
        return false;
      }

      const query = `
        INSERT INTO public.slack_message_feedback (
          message_id, channel_id, user_id, feedback_type, created_at
        ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        ON CONFLICT (message_id, user_id) DO UPDATE SET
          feedback_type = EXCLUDED.feedback_type,
          created_at = CURRENT_TIMESTAMP
      `;

      const values = [
        feedbackData.messageId,
        feedbackData.channelId,
        feedbackData.userId,
        feedbackData.feedbackType,
      ];

      const result = await pool.query(query, values);

      logger.info('Successfully stored button feedback', {
        tenantId,
        messageId: feedbackData.messageId,
        channelId: feedbackData.channelId,
        userId: feedbackData.userId,
        feedbackType: feedbackData.feedbackType,
        wasInserted: result.rowCount === 1,
        operation: 'store-feedback',
      });

      return true;
    } catch (error) {
      logger.error(
        'Failed to store button feedback',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          messageId: feedbackData.messageId,
          channelId: feedbackData.channelId,
          userId: feedbackData.userId,
          feedbackType: feedbackData.feedbackType,
          operation: 'store-feedback',
        }
      );
      return false;
    }
  }

  /**
   * Remove user feedback (if they want to change their mind)
   */
  async removeFeedback(tenantId: string, messageId: string, userId: string): Promise<boolean> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);
      this.validateFeedbackRemovalData(messageId, userId);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'remove-feedback',
        });
        return false;
      }

      const query = `
        DELETE FROM public.slack_message_feedback
        WHERE message_id = $1 AND user_id = $2
      `;

      const values = [messageId, userId];
      const result = await pool.query(query, values);

      logger.info('Successfully removed button feedback', {
        tenantId,
        messageId,
        userId,
        wasDeleted: result.rowCount === 1,
        operation: 'remove-feedback',
      });

      return true;
    } catch (error) {
      logger.error(
        'Failed to remove button feedback',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          messageId,
          userId,
          operation: 'remove-feedback',
        }
      );
      return false;
    }
  }

  async getSourcesStats(
    tenantId: string
  ): Promise<Record<string, { indexed: number; discovered: Record<string, number> }> | null> {
    try {
      this.validateTenantId(tenantId);
      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'get-sources-stats',
        });
        return null;
      }
      // The following code borrows heavily from the admin-frontend stats API

      // Query for indexed documents grouped by source
      const indexedQuery = `
        SELECT 
          source,
          COUNT(*) as count
        FROM public.documents
        GROUP BY source
        ORDER BY source
      `;

      // Query for discovered artifacts grouped by entity
      const discoveredQuery = `
        SELECT 
          entity,
          COUNT(*) as count
        FROM public.ingest_artifact
        GROUP BY entity
        ORDER BY entity
      `;

      // Execute both queries in parallel
      const [indexedResult, discoveredResult] = await Promise.all([
        pool.query(indexedQuery),
        pool.query(discoveredQuery),
      ]);

      // Function to map entity types to their source
      const getSourceFromEntity = (entity: string): string => {
        if (entity.startsWith('github_')) return 'github';
        if (entity.startsWith('slack_')) return 'slack';
        if (entity.startsWith('notion_')) return 'notion';
        if (entity.startsWith('linear_')) return 'linear';
        if (entity.startsWith('google_')) return 'google_drive';
        if (entity.startsWith('hubspot_')) return 'hubspot';
        if (entity.startsWith('salesforce_')) return 'salesforce';
        // Default fallback - use the entity name as source
        return entity;
      };

      // Build the response structure
      const sourceStats: Record<string, { indexed: number; discovered: Record<string, number> }> =
        {};

      // Process indexed documents
      for (const row of indexedResult.rows) {
        const source = row.source;
        if (!sourceStats[source]) {
          sourceStats[source] = { indexed: 0, discovered: {} };
        }
        sourceStats[source].indexed = parseInt(row.count) || 0;
      }

      // Process discovered artifacts
      for (const row of discoveredResult.rows) {
        const entity = row.entity;
        const source = getSourceFromEntity(entity);
        const count = parseInt(row.count) || 0;

        if (!sourceStats[source]) {
          sourceStats[source] = { indexed: 0, discovered: {} };
        }
        sourceStats[source].discovered[entity] = count;
      }

      return sourceStats;
    } catch (error) {
      logger.error(
        'Failed to get sources stats',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          operation: 'get-sources-stats',
        }
      );
      return null;
    }
  }

  /**
   * Get the model response ID for a bot message
   * Delegates to the backend-common DAL for database operations
   * @param tenantId - The tenant ID
   * @param botResponseMessageId - The bot's response message timestamp
   * @returns The model response ID if found, null otherwise
   */
  async getResponseId(tenantId: string, botResponseMessageId: string): Promise<string | null> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);

      if (
        !botResponseMessageId ||
        typeof botResponseMessageId !== 'string' ||
        botResponseMessageId.trim() === ''
      ) {
        throw new Error('Invalid botResponseMessageId: must be a non-empty string');
      }

      if (!this.isValidSlackTimestamp(botResponseMessageId)) {
        throw new Error('Invalid botResponseMessageId format: must be a valid Slack timestamp');
      }

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'get-response-id',
        });
        return null;
      }

      // Use DAL function for database query
      const responseId = await SlackMessagesDAL.getModelResponseIdByBotMessageId(
        pool,
        botResponseMessageId
      );

      return responseId;
    } catch (error) {
      logger.error(
        'Failed to get response ID',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          botResponseMessageId,
          operation: 'get-response-id',
        }
      );
      return null;
    }
  }

  /**
   * Get message statistics for a tenant (useful for monitoring)
   */
  async getMessageStats(tenantId: string): Promise<{
    totalMessages: number;
    totalReactions: number;
    positiveReactions: number;
    negativeReactions: number;
  } | null> {
    try {
      // Validate inputs
      this.validateTenantId(tenantId);

      const pool = await tenantDbConnectionManager.get(tenantId);
      if (!pool) {
        logger.warn('No database pool available for tenant', {
          tenantId,
          operation: 'get-stats',
        });
        return null;
      }

      const statsQuery = `
        SELECT 
          (SELECT COUNT(*) FROM public.slack_messages) as total_messages,
          (SELECT COUNT(*) FROM public.slack_message_reactions) as total_reactions,
          (SELECT COUNT(*) FROM public.slack_message_reactions WHERE reaction IN ('+1', 'thumbsup')) as positive_reactions,
          (SELECT COUNT(*) FROM public.slack_message_reactions WHERE reaction IN ('-1', 'thumbsdown')) as negative_reactions
      `;

      const result = await pool.query(statsQuery);
      const stats = result.rows[0];

      return {
        totalMessages: parseInt(stats.total_messages) || 0,
        totalReactions: parseInt(stats.total_reactions) || 0,
        positiveReactions: parseInt(stats.positive_reactions) || 0,
        negativeReactions: parseInt(stats.negative_reactions) || 0,
      };
    } catch (error) {
      logger.error(
        'Failed to get message stats',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          operation: 'get-stats',
        }
      );
      return null;
    }
  }

  /**
   * Close database connections (for cleanup)
   */
  async shutdown(): Promise<void> {
    await tenantDbConnectionManager.closeAll();
    logger.info('SlackMessageStorage shutdown complete', { operation: 'shutdown' });
  }
}

// Singleton instance for the service
let instance: SlackMessageStorage | null = null;

/**
 * Get the singleton SlackMessageStorage instance
 */
export function getSlackMessageStorage(): SlackMessageStorage {
  if (!instance) {
    instance = new SlackMessageStorage();
  }
  return instance;
}
