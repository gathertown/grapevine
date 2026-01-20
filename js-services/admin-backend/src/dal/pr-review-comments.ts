/**
 * Data Access Layer for PR Review Comments
 *
 * Handles database operations for pr_review_comments and pr_review_comment_reactions tables
 * in tenant databases.
 */

import { Pool } from 'pg';

import { logger } from '../utils/logger.js';
import {
  PrReviewComment,
  PrReviewCommentWithReactions,
  ReactionAnalytics,
  CreatePrReviewCommentRequest,
} from '../types/pr-review.js';

/**
 * Map database row to PrReviewComment
 */
function mapCommentRow(row: Record<string, unknown>): PrReviewComment {
  return {
    id: row.id as string,
    githubCommentId: Number(row.github_comment_id),
    githubReviewId: Number(row.github_review_id),
    githubPrNumber: row.github_pr_number as number,
    githubRepoOwner: row.github_repo_owner as string,
    githubRepoName: row.github_repo_name as string,
    filePath: row.file_path as string,
    lineNumber: row.line_number as number | null,
    position: row.position as number | null,
    impact: row.impact as number | null,
    confidence: row.confidence as number | null,
    categories: row.categories as string[] | null,
    githubCommentUrl: row.github_comment_url as string | null,
    githubReviewUrl: row.github_review_url as string | null,
    lastSyncedAt: row.last_synced_at ? (row.last_synced_at as Date).toISOString() : null,
    createdAt: (row.created_at as Date).toISOString(),
    updatedAt: (row.updated_at as Date).toISOString(),
  };
}

/**
 * Create a new PR review comment
 * Returns null if comment with same github_comment_id already exists
 */
export async function createPrReviewComment(
  pool: Pool,
  data: Omit<CreatePrReviewCommentRequest, 'tenantId'>
): Promise<PrReviewComment | null> {
  try {
    // Use INSERT ... ON CONFLICT to handle duplicates atomically
    // Assumes there's a unique constraint on github_comment_id
    const result = await pool.query(
      `INSERT INTO pr_review_comments (
        github_comment_id, github_review_id, github_pr_number,
        github_repo_owner, github_repo_name, file_path,
        line_number, position, impact, confidence,
        categories, github_comment_url, github_review_url
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
      ON CONFLICT (github_comment_id) DO NOTHING
      RETURNING *`,
      [
        data.githubCommentId,
        data.githubReviewId,
        data.githubPrNumber,
        data.githubRepoOwner,
        data.githubRepoName,
        data.filePath,
        data.lineNumber ?? null,
        data.position ?? null,
        data.impact ?? null,
        data.confidence ?? null,
        data.categories ? JSON.stringify(data.categories) : null,
        data.githubCommentUrl ?? null,
        data.githubReviewUrl ?? null,
      ]
    );

    // If no rows returned, comment already existed
    if (result.rows.length === 0) {
      logger.info('PR review comment already exists', {
        githubCommentId: data.githubCommentId,
      });
      return null;
    }

    logger.info('Created PR review comment', {
      id: result.rows[0].id,
      githubCommentId: data.githubCommentId,
    });

    return mapCommentRow(result.rows[0]);
  } catch (error) {
    logger.error('Error creating PR review comment', {
      error: String(error),
      data,
    });
    throw error;
  }
}

/**
 * Get all comments for a PR with reaction counts
 */
export async function getCommentsForPr(
  pool: Pool,
  owner: string,
  repo: string,
  prNumber: number
): Promise<PrReviewCommentWithReactions[]> {
  try {
    const result = await pool.query(
      `SELECT
        c.*,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) as thumbs_up_count,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as thumbs_down_count,
        COUNT(CASE WHEN r.reaction_type = 'laugh' THEN 1 END) as laugh_count,
        COUNT(CASE WHEN r.reaction_type = 'confused' THEN 1 END) as confused_count,
        COUNT(CASE WHEN r.reaction_type = 'heart' THEN 1 END) as heart_count,
        COUNT(CASE WHEN r.reaction_type = 'hooray' THEN 1 END) as hooray_count,
        COUNT(CASE WHEN r.reaction_type = 'rocket' THEN 1 END) as rocket_count,
        COUNT(CASE WHEN r.reaction_type = 'eyes' THEN 1 END) as eyes_count,
        COUNT(r.id) as total_reaction_count
      FROM pr_review_comments c
      LEFT JOIN pr_review_comment_reactions r ON r.comment_id = c.id
      WHERE c.github_repo_owner = $1
        AND c.github_repo_name = $2
        AND c.github_pr_number = $3
      GROUP BY c.id
      ORDER BY c.created_at DESC`,
      [owner, repo, prNumber]
    );

    return result.rows.map((row) => ({
      ...mapCommentRow(row),
      reactions: {
        thumbsUpCount: Number(row.thumbs_up_count),
        thumbsDownCount: Number(row.thumbs_down_count),
        laughCount: Number(row.laugh_count),
        confusedCount: Number(row.confused_count),
        heartCount: Number(row.heart_count),
        hoorayCount: Number(row.hooray_count),
        rocketCount: Number(row.rocket_count),
        eyesCount: Number(row.eyes_count),
        totalCount: Number(row.total_reaction_count),
      },
    }));
  } catch (error) {
    logger.error('Error getting comments for PR', {
      error: String(error),
      owner,
      repo,
      prNumber,
    });
    throw error;
  }
}

/**
 * Get reaction analytics for a tenant
 */
export async function getReactionAnalytics(
  pool: Pool,
  limit: number = 10
): Promise<ReactionAnalytics> {
  try {
    // Get overall stats including net positive/negative comment counts
    const statsResult = await pool.query(
      `WITH comment_scores AS (
        SELECT
          c.id,
          COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) as thumbs_up,
          COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as thumbs_down,
          COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) -
          COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as net_score
        FROM pr_review_comments c
        LEFT JOIN pr_review_comment_reactions r ON r.comment_id = c.id
        GROUP BY c.id
      )
      SELECT
        COUNT(DISTINCT c.id) as total_comments,
        COUNT(r.id) as total_reactions,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) as thumbs_up_total,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as thumbs_down_total,
        COUNT(CASE WHEN r.reaction_type = 'laugh' THEN 1 END) as laugh_total,
        COUNT(CASE WHEN r.reaction_type = 'confused' THEN 1 END) as confused_total,
        COUNT(CASE WHEN r.reaction_type = 'heart' THEN 1 END) as heart_total,
        COUNT(CASE WHEN r.reaction_type = 'hooray' THEN 1 END) as hooray_total,
        COUNT(CASE WHEN r.reaction_type = 'rocket' THEN 1 END) as rocket_total,
        COUNT(CASE WHEN r.reaction_type = 'eyes' THEN 1 END) as eyes_total,
        (SELECT COUNT(*) FROM comment_scores WHERE net_score > 0) as net_positive_comments,
        (SELECT COUNT(*) FROM comment_scores WHERE net_score < 0) as net_negative_comments
      FROM pr_review_comments c
      LEFT JOIN pr_review_comment_reactions r ON r.comment_id = c.id`
    );

    const stats = statsResult.rows[0];
    const totalComments = Number(stats.total_comments);
    const totalReactions = Number(stats.total_reactions);
    const netPositiveComments = Number(stats.net_positive_comments);
    const netNegativeComments = Number(stats.net_negative_comments);

    // Get top reacted comments
    const topCommentsResult = await pool.query(
      `SELECT
        c.*,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) as thumbs_up_count,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as thumbs_down_count,
        COUNT(CASE WHEN r.reaction_type = 'laugh' THEN 1 END) as laugh_count,
        COUNT(CASE WHEN r.reaction_type = 'confused' THEN 1 END) as confused_count,
        COUNT(CASE WHEN r.reaction_type = 'heart' THEN 1 END) as heart_count,
        COUNT(CASE WHEN r.reaction_type = 'hooray' THEN 1 END) as hooray_count,
        COUNT(CASE WHEN r.reaction_type = 'rocket' THEN 1 END) as rocket_count,
        COUNT(CASE WHEN r.reaction_type = 'eyes' THEN 1 END) as eyes_count,
        COUNT(r.id) as total_reaction_count,
        (COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) -
         COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END)) as reaction_score
      FROM pr_review_comments c
      LEFT JOIN pr_review_comment_reactions r ON r.comment_id = c.id
      GROUP BY c.id
      HAVING COUNT(r.id) > 0
      ORDER BY reaction_score DESC, total_reaction_count DESC
      LIMIT $1`,
      [limit]
    );

    const topReactedComments = topCommentsResult.rows.map((row) => ({
      comment: {
        ...mapCommentRow(row),
        reactions: {
          thumbsUpCount: Number(row.thumbs_up_count),
          thumbsDownCount: Number(row.thumbs_down_count),
          laughCount: Number(row.laugh_count),
          confusedCount: Number(row.confused_count),
          heartCount: Number(row.heart_count),
          hoorayCount: Number(row.hooray_count),
          rocketCount: Number(row.rocket_count),
          eyesCount: Number(row.eyes_count),
          totalCount: Number(row.total_reaction_count),
        },
      },
      reactionScore: Number(row.reaction_score),
    }));

    // Get bottom reacted comments (worst reaction scores)
    const bottomCommentsResult = await pool.query(
      `SELECT
        c.*,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) as thumbs_up_count,
        COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END) as thumbs_down_count,
        COUNT(CASE WHEN r.reaction_type = 'laugh' THEN 1 END) as laugh_count,
        COUNT(CASE WHEN r.reaction_type = 'confused' THEN 1 END) as confused_count,
        COUNT(CASE WHEN r.reaction_type = 'heart' THEN 1 END) as heart_count,
        COUNT(CASE WHEN r.reaction_type = 'hooray' THEN 1 END) as hooray_count,
        COUNT(CASE WHEN r.reaction_type = 'rocket' THEN 1 END) as rocket_count,
        COUNT(CASE WHEN r.reaction_type = 'eyes' THEN 1 END) as eyes_count,
        COUNT(r.id) as total_reaction_count,
        (COUNT(CASE WHEN r.reaction_type = 'thumbs_up' THEN 1 END) -
         COUNT(CASE WHEN r.reaction_type = 'thumbs_down' THEN 1 END)) as reaction_score
      FROM pr_review_comments c
      LEFT JOIN pr_review_comment_reactions r ON r.comment_id = c.id
      GROUP BY c.id
      HAVING COUNT(r.id) > 0
      ORDER BY reaction_score ASC, total_reaction_count DESC
      LIMIT $1`,
      [limit]
    );

    const bottomReactedComments = bottomCommentsResult.rows.map((row) => ({
      comment: {
        ...mapCommentRow(row),
        reactions: {
          thumbsUpCount: Number(row.thumbs_up_count),
          thumbsDownCount: Number(row.thumbs_down_count),
          laughCount: Number(row.laugh_count),
          confusedCount: Number(row.confused_count),
          heartCount: Number(row.heart_count),
          hoorayCount: Number(row.hooray_count),
          rocketCount: Number(row.rocket_count),
          eyesCount: Number(row.eyes_count),
          totalCount: Number(row.total_reaction_count),
        },
      },
      reactionScore: Number(row.reaction_score),
    }));

    return {
      totalComments,
      totalReactions,
      thumbsUpTotal: Number(stats.thumbs_up_total),
      thumbsDownTotal: Number(stats.thumbs_down_total),
      laughTotal: Number(stats.laugh_total),
      confusedTotal: Number(stats.confused_total),
      heartTotal: Number(stats.heart_total),
      hoorayTotal: Number(stats.hooray_total),
      rocketTotal: Number(stats.rocket_total),
      eyesTotal: Number(stats.eyes_total),
      avgReactionsPerComment: totalComments > 0 ? totalReactions / totalComments : 0,
      netPositiveComments,
      netNegativeComments,
      topReactedComments,
      bottomReactedComments,
    };
  } catch (error) {
    logger.error('Error getting reaction analytics', {
      error: String(error),
    });
    throw error;
  }
}
