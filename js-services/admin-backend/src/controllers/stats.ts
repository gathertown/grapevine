import { Router, Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { dbMiddleware } from '../middleware/db-middleware.js';
import { logger, LogContext } from '../utils/logger.js';

const statsRouter = Router();

// Define interfaces for our data structures

interface SlackReaction {
  message_id: string;
  channel_id: string;
  user_id: string;
  reaction: string;
  created_at: string;
}

interface SlackFeedback {
  message_id: string;
  channel_id: string;
  user_id: string;
  feedback_type: string;
  created_at: string;
}

interface ThreadStat {
  message_id: string;
  channel_id: string;
  user_id: string;
  question: string;
  answer: string;
  created_at: string;
  is_proactive: boolean;
  channel_name?: string;
  user_name?: string;
  user_display_name?: string;
  reactions: SlackReaction[];
  button_feedback: SlackFeedback[];
}

interface ThreadMessage {
  message_id: string;
  channel_id: string;
  user_id: string;
  text: string;
  timestamp: string;
  thread_ts?: string;
  is_bot: boolean;
  user_name?: string;
  user_display_name?: string;
  reactions: SlackReaction[];
}

interface ThreadDetails {
  original_question_message_id: string;
  bot_response_message_id: string;
  channel_id: string;
  thread_ts: string;
  messages: ThreadMessage[];
}

interface ThreadStatsResponse {
  threads: ThreadStat[];
  total: number;
  hasMore: boolean;
}

/**
 * GET /api/stats/threads
 * Get all bot Q&A interactions in thread context with reactions
 */
statsRouter.get('/threads', requireAdmin, dbMiddleware, async (req: Request, res: Response) => {
  return LogContext.run({ operation: 'get-thread-stats', endpoint: '/stats/threads' }, async () => {
    try {
      const tenantId = req.user?.tenantId;
      if (!tenantId) {
        return res.status(400).json({ error: 'No tenant found for organization' });
      }

      const db = req.db;
      if (!db) {
        return res.status(500).json({ error: 'Database connection not available' });
      }

      // Parse query parameters
      const page = Math.max(1, parseInt(req.query.page as string) || 1);
      const limit = Math.min(100, Math.max(1, parseInt(req.query.limit as string) || 20));
      const offset = (page - 1) * limit;

      // Optional date filtering
      const dateFrom = req.query.date_from as string;
      const dateTo = req.query.date_to as string;

      // Build date filtering conditions
      let dateConditions = '';
      const queryParams: unknown[] = [];
      let paramIndex = 1;

      if (dateFrom) {
        dateConditions += ` AND sm.created_at >= $${paramIndex}`;
        queryParams.push(dateFrom);
        paramIndex++;
      }

      if (dateTo) {
        dateConditions += ` AND sm.created_at <= $${paramIndex}`;
        queryParams.push(dateTo);
        paramIndex++;
      }

      // Main query to get messages with human-readable names
      const mainQuery = `
      SELECT
        sm.message_id,
        sm.channel_id,
        sm.user_id,
        sm.question,
        sm.answer,
        sm.created_at,
        sm.is_proactive,
        sm.bot_response_message_id,
        channel_ia.content ->> 'name' as channel_name,
        user_ia.content ->> 'name' as user_name,
        user_ia.content ->> 'real_name' as user_display_name
      FROM public.slack_messages sm
      LEFT JOIN public.ingest_artifact channel_ia ON (
        channel_ia.entity = 'slack_channel'
        AND channel_ia.entity_id = sm.channel_id
      )
      LEFT JOIN public.ingest_artifact user_ia ON (
        user_ia.entity = 'slack_user'
        AND user_ia.entity_id = sm.user_id
      )
      WHERE 1=1 ${dateConditions}
      ORDER BY sm.created_at DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

      queryParams.push(limit, offset);

      // Count query for total
      const countQuery = `
      SELECT COUNT(DISTINCT sm.message_id) as total
      FROM public.slack_messages sm
      WHERE 1=1 ${dateConditions}
    `;

      // Execute main query and count in parallel
      const [mainResult, countResult] = await Promise.all([
        db.query(mainQuery, queryParams),
        db.query(countQuery, queryParams.slice(0, -2)), // Remove limit and offset for count
      ]);

      // Get bot_response_message_ids for fetching reactions and feedback
      const botResponseMessageIds = mainResult.rows
        .map((row) => row.bot_response_message_id)
        .filter((id) => id != null);

      // Fetch reactions and feedback in parallel (only if we have message IDs)
      let reactionsResult, feedbackResult;
      if (botResponseMessageIds.length > 0) {
        [reactionsResult, feedbackResult] = await Promise.all([
          db.query(
            `
          SELECT message_id, channel_id, user_id, reaction, created_at
          FROM public.slack_message_reactions
          WHERE message_id = ANY($1)
          ORDER BY created_at DESC
        `,
            [botResponseMessageIds]
          ),
          db.query(
            `
          SELECT message_id, channel_id, user_id, feedback_type, created_at
          FROM public.slack_message_feedback
          WHERE message_id = ANY($1)
          ORDER BY created_at DESC
        `,
            [botResponseMessageIds]
          ),
        ]);
      } else {
        reactionsResult = { rows: [] };
        feedbackResult = { rows: [] };
      }

      // Group reactions and feedback by message_id
      const reactionsByMessage = new Map<string, SlackReaction[]>();
      for (const reaction of reactionsResult.rows) {
        const existing = reactionsByMessage.get(reaction.message_id);
        if (existing) {
          existing.push(reaction);
        } else {
          reactionsByMessage.set(reaction.message_id, [reaction]);
        }
      }

      const feedbackByMessage = new Map<string, SlackFeedback[]>();
      for (const feedback of feedbackResult.rows) {
        const existing = feedbackByMessage.get(feedback.message_id);
        if (existing) {
          existing.push(feedback);
        } else {
          feedbackByMessage.set(feedback.message_id, [feedback]);
        }
      }

      // Combine all data
      const threads: ThreadStat[] = mainResult.rows.map((row) => ({
        message_id: row.message_id,
        channel_id: row.channel_id,
        user_id: row.user_id,
        question: row.question,
        answer: row.answer,
        created_at: row.created_at,
        is_proactive: row.is_proactive,
        channel_name: row.channel_name,
        user_name: row.user_name,
        user_display_name: row.user_display_name,
        reactions: reactionsByMessage.get(row.bot_response_message_id) || [],
        button_feedback: feedbackByMessage.get(row.bot_response_message_id) || [],
      }));

      const total = parseInt(countResult.rows[0]?.total || '0');
      const hasMore = offset + threads.length < total;

      const response: ThreadStatsResponse = {
        threads,
        total,
        hasMore,
      };

      res.json(response);
    } catch (error) {
      logger.error('Error retrieving thread stats', error);
      res.status(500).json({ error: 'Failed to retrieve thread stats' });
    }
  });
});

/**
 * GET /api/stats/summary
 * Get summary statistics about Q&A interactions
 */
statsRouter.get('/summary', requireAdmin, dbMiddleware, async (req: Request, res: Response) => {
  return LogContext.run(
    { operation: 'get-summary-stats', endpoint: '/stats/summary' },
    async () => {
      try {
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({ error: 'No tenant found for organization' });
        }

        const db = req.db;
        if (!db) {
          return res.status(500).json({ error: 'Database connection not available' });
        }

        // Optional date filtering
        const dateFrom = req.query.date_from as string;
        const dateTo = req.query.date_to as string;

        // Build date filtering conditions
        let dateConditions = '';
        const queryParams: unknown[] = [];
        let paramIndex = 1;

        if (dateFrom) {
          dateConditions += ` AND sm.created_at >= $${paramIndex}`;
          queryParams.push(dateFrom);
          paramIndex++;
        }

        if (dateTo) {
          dateConditions += ` AND sm.created_at <= $${paramIndex}`;
          queryParams.push(dateTo);
          paramIndex++;
        }

        const summaryQuery = `
      SELECT
        COUNT(DISTINCT sm.message_id) as total_messages,
        COUNT(DISTINCT CASE WHEN sm.channel_id LIKE 'C%' THEN sm.message_id END) as channel_messages,
        COUNT(DISTINCT CASE WHEN sm.channel_id LIKE 'D%' THEN sm.message_id END) as dm_messages,
        COUNT(DISTINCT smr.message_id) as messages_with_reactions,
        COUNT(DISTINCT CASE WHEN smr.reaction IN (
          '+1', 'thumbsup', 'fire', 'heavy_check_mark', 'clap', 'heart', 'star', 'pray', 'thankyou',
          'thumbsup::skin-tone-2', 'thumbsup::skin-tone-3', 'thumbsup::skin-tone-4', 'thumbsup::skin-tone-5', 'thumbsup::skin-tone-6'
        ) THEN smr.message_id END) as messages_with_positive_reactions,
        COUNT(DISTINCT CASE WHEN smr.reaction IN (
          '-1', 'thumbsdown', 'x', 'confused', 'thinking_face',
          'thumbsdown::skin-tone-2', 'thumbsdown::skin-tone-3', 'thumbsdown::skin-tone-4', 'thumbsdown::skin-tone-5', 'thumbsdown::skin-tone-6'
        ) THEN smr.message_id END) as messages_with_negative_reactions,
        COUNT(smr.reaction) as total_reactions,
        COUNT(CASE WHEN smr.reaction IN (
          '+1', 'thumbsup', 'fire', 'heavy_check_mark', 'clap', 'heart', 'star', 'pray', 'thankyou',
          'thumbsup::skin-tone-2', 'thumbsup::skin-tone-3', 'thumbsup::skin-tone-4', 'thumbsup::skin-tone-5', 'thumbsup::skin-tone-6'
        ) THEN 1 END) as positive_reactions,
        COUNT(CASE WHEN smr.reaction IN (
          '-1', 'thumbsdown', 'x', 'confused', 'thinking_face',
          'thumbsdown::skin-tone-2', 'thumbsdown::skin-tone-3', 'thumbsdown::skin-tone-4', 'thumbsdown::skin-tone-5', 'thumbsdown::skin-tone-6'
        ) THEN 1 END) as negative_reactions,
        COUNT(DISTINCT smf.message_id) as messages_with_button_feedback,
        COUNT(DISTINCT CASE WHEN smf.feedback_type = 'positive' THEN smf.message_id END) as messages_with_positive_feedback,
        COUNT(DISTINCT CASE WHEN smf.feedback_type = 'negative' THEN smf.message_id END) as messages_with_negative_feedback,
        COUNT(smf.id) as total_button_feedback,
        COUNT(CASE WHEN smf.feedback_type = 'positive' THEN 1 END) as positive_button_feedback,
        COUNT(CASE WHEN smf.feedback_type = 'negative' THEN 1 END) as negative_button_feedback,
        COUNT(DISTINCT sm.channel_id) as unique_channels,
        COUNT(DISTINCT sm.user_id) as unique_users
      FROM public.slack_messages sm
      LEFT JOIN public.slack_message_reactions smr ON sm.bot_response_message_id = smr.message_id
      LEFT JOIN public.slack_message_feedback smf ON sm.bot_response_message_id = smf.message_id
      WHERE 1=1 ${dateConditions}
    `;

        const result = await db.query(summaryQuery, queryParams);
        const stats = result.rows[0];

        const summary = {
          totalMessages: parseInt(stats.total_messages) || 0,
          channelMessages: parseInt(stats.channel_messages) || 0,
          dmMessages: parseInt(stats.dm_messages) || 0,
          messagesWithReactions: parseInt(stats.messages_with_reactions) || 0,
          messagesWithPositiveReactions: parseInt(stats.messages_with_positive_reactions) || 0,
          messagesWithNegativeReactions: parseInt(stats.messages_with_negative_reactions) || 0,
          totalReactions: parseInt(stats.total_reactions) || 0,
          positiveReactions: parseInt(stats.positive_reactions) || 0,
          negativeReactions: parseInt(stats.negative_reactions) || 0,
          messagesWithButtonFeedback: parseInt(stats.messages_with_button_feedback) || 0,
          messagesWithPositiveFeedback: parseInt(stats.messages_with_positive_feedback) || 0,
          messagesWithNegativeFeedback: parseInt(stats.messages_with_negative_feedback) || 0,
          totalButtonFeedback: parseInt(stats.total_button_feedback) || 0,
          positiveButtonFeedback: parseInt(stats.positive_button_feedback) || 0,
          negativeButtonFeedback: parseInt(stats.negative_button_feedback) || 0,
          uniqueChannels: parseInt(stats.unique_channels) || 0,
          uniqueUsers: parseInt(stats.unique_users) || 0,
        };

        res.json(summary);
      } catch (error) {
        logger.error('Error retrieving summary stats', error);
        res.status(500).json({ error: 'Failed to retrieve summary stats' });
      }
    }
  );
});

/**
 * GET /api/stats/threads/:message_id/full
 * Get full thread details including all messages in the thread
 */
statsRouter.get(
  '/threads/:message_id/full',
  requireAdmin,
  dbMiddleware,
  async (req: Request, res: Response) => {
    return LogContext.run(
      { operation: 'get-thread-details', endpoint: '/stats/threads/:message_id/full' },
      async () => {
        try {
          const tenantId = req.user?.tenantId;
          if (!tenantId) {
            return res.status(400).json({ error: 'No tenant found for organization' });
          }

          const db = req.db;
          if (!db) {
            return res.status(500).json({ error: 'Database connection not available' });
          }

          const messageId = req.params.message_id;
          if (!messageId) {
            return res.status(400).json({ error: 'Message ID is required' });
          }

          // First, get the original Q&A record to find the thread timestamp
          const qaQuery = `
      SELECT 
        sm.message_id,
        sm.channel_id,
        sm.bot_response_message_id,
        ia.content ->> 'thread_ts' as thread_ts
      FROM public.slack_messages sm
      JOIN public.ingest_artifact ia ON ia.content ->> 'ts' = sm.message_id
      WHERE sm.message_id = $1
        AND ia.entity = 'slack_message'
    `;

          const qaResult = await db.query(qaQuery, [messageId]);

          if (qaResult.rows.length === 0) {
            return res.status(404).json({ error: 'Thread not found' });
          }

          const qaRecord = qaResult.rows[0];
          const threadTs = qaRecord.thread_ts || qaRecord.message_id; // Use message_id as thread_ts if no thread

          // Get all messages in the thread from ingest_artifact
          const threadQuery = `
      SELECT 
        ia.content ->> 'ts' as message_id,
        ia.content ->> 'channel' as channel_id,
        ia.content ->> 'user' as user_id,
        ia.content ->> 'text' as text,
        ia.content ->> 'ts' as timestamp,
        ia.content ->> 'thread_ts' as thread_ts,
        CASE 
          WHEN ia.content ->> 'bot_id' IS NOT NULL OR ia.content ->> 'subtype' = 'bot_message' 
          THEN true 
          ELSE false 
        END as is_bot,
        user_ia.content ->> 'name' as user_name,
        user_ia.content ->> 'real_name' as user_display_name,
        COALESCE(
          json_agg(
            json_build_object(
              'message_id', smr.message_id,
              'channel_id', smr.channel_id,
              'user_id', smr.user_id,
              'reaction', smr.reaction,
              'created_at', smr.created_at
            ) ORDER BY smr.created_at DESC
          ) FILTER (WHERE smr.message_id IS NOT NULL),
          '[]'::json
        ) as reactions
      FROM public.ingest_artifact ia
      LEFT JOIN public.slack_message_reactions smr ON smr.message_id = ia.content ->> 'ts'
      LEFT JOIN public.ingest_artifact user_ia ON (
        user_ia.entity = 'slack_user' 
        AND user_ia.entity_id = ia.content ->> 'user'
      )
      WHERE ia.entity = 'slack_message'
        AND ia.content ->> 'channel' = $1
        AND (
          ia.content ->> 'thread_ts' = $2 
          OR (ia.content ->> 'thread_ts' IS NULL AND ia.content ->> 'ts' = $2)
        )
      GROUP BY ia.content, user_ia.content
      ORDER BY (ia.content ->> 'ts')::double precision ASC
    `;

          const threadResult = await db.query(threadQuery, [qaRecord.channel_id, threadTs]);

          // Transform the results
          const messages: ThreadMessage[] = threadResult.rows.map((row) => ({
            message_id: row.message_id,
            channel_id: row.channel_id,
            user_id: row.user_id || 'unknown',
            text: row.text || '',
            timestamp: row.timestamp,
            thread_ts: row.thread_ts,
            is_bot: row.is_bot,
            user_name: row.user_name,
            user_display_name: row.user_display_name,
            reactions: Array.isArray(row.reactions) ? row.reactions : [],
          }));

          const threadDetails: ThreadDetails = {
            original_question_message_id: qaRecord.message_id,
            bot_response_message_id: qaRecord.bot_response_message_id,
            channel_id: qaRecord.channel_id,
            thread_ts: threadTs,
            messages,
          };

          res.json(threadDetails);
        } catch (error) {
          logger.error('Error retrieving thread details', error, {
            messageId: req.params.message_id,
          });
          res.status(500).json({ error: 'Failed to retrieve thread details' });
        }
      }
    );
  }
);

/**
 * GET /api/stats/sources
 * Get indexing and discovery statistics for each source
 */
statsRouter.get('/sources', requireAdmin, dbMiddleware, async (req: Request, res: Response) => {
  return LogContext.run({ operation: 'get-source-stats', endpoint: '/stats/sources' }, async () => {
    try {
      const tenantId = req.user?.tenantId;
      if (!tenantId) {
        return res.status(400).json({ error: 'No tenant found for organization' });
      }

      const db = req.db;
      if (!db) {
        return res.status(500).json({ error: 'Database connection not available' });
      }

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
        db.query(indexedQuery),
        db.query(discoveredQuery),
      ]);

      // Function to map ingest artifact entity types AND document types to connector keys
      const getConnectorKeyFromType = (source: string): string => {
        if (source.startsWith('github')) return 'github';
        if (source.startsWith('slack')) return 'slack';
        if (source.startsWith('notion')) return 'notion';
        if (source.startsWith('linear')) return 'linear';
        if (source.startsWith('google_drive')) return 'google_drive';
        if (source.startsWith('hubspot')) return 'hubspot';
        if (source.startsWith('salesforce')) return 'salesforce';
        if (source.startsWith('jira')) return 'jira';
        if (source.startsWith('confluence')) return 'confluence';
        if (source.startsWith('google_email')) return 'google_email';
        if (source.startsWith('gong')) return 'gong';
        if (source.startsWith('gather')) return 'gather';
        if (source.startsWith('trello')) return 'trello';
        if (source.startsWith('zendesk')) return 'zendesk';
        if (source.startsWith('asana')) return 'asana';
        if (source.startsWith('intercom')) return 'intercom';
        if (source.startsWith('attio')) return 'attio';
        if (source.startsWith('fireflies')) return 'fireflies';
        if (source.startsWith('gitlab')) return 'gitlab';
        if (source.startsWith('pylon')) return 'pylon';
        if (source.startsWith('custom_data')) return 'custom_data';
        if (source.startsWith('monday')) return 'monday';
        if (source.startsWith('pipedrive')) return 'pipedrive';
        if (source.startsWith('clickup')) return 'clickup';
        if (source.startsWith('figma')) return 'figma';
        if (source.startsWith('posthog')) return 'posthog';
        if (source.startsWith('canva')) return 'canva';
        if (source.startsWith('teamwork')) return 'teamwork';

        return source;
      };

      // Build the response structure
      const sourceStats: Record<string, { indexed: number; discovered: Record<string, number> }> =
        {};

      // Process indexed documents
      for (const row of indexedResult.rows) {
        const source = getConnectorKeyFromType(row.source);
        if (!sourceStats[source]) {
          sourceStats[source] = { indexed: 0, discovered: {} };
        }
        sourceStats[source].indexed = parseInt(row.count) || 0;
      }

      // Process discovered artifacts
      for (const row of discoveredResult.rows) {
        const entity = row.entity;
        const source = getConnectorKeyFromType(entity);
        const count = parseInt(row.count) || 0;

        if (!sourceStats[source]) {
          sourceStats[source] = { indexed: 0, discovered: {} };
        }
        sourceStats[source].discovered[entity] = count;
      }

      res.json(sourceStats);
    } catch (error) {
      logger.error('Error retrieving source stats', error);
      res.status(500).json({ error: 'Failed to retrieve source stats' });
    }
  });
});

export { statsRouter };
