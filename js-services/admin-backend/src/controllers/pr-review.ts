/**
 * PR Review Controller
 *
 * REST endpoints for managing PR review comments and reactions
 */

import { Router, Response } from 'express';
import { z } from 'zod';

import { requireApiKey } from '../middleware/requireApiKey.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { logger } from '../utils/logger.js';
import {
  createPrReviewComment,
  getCommentsForPr,
  getReactionAnalytics,
} from '../dal/pr-review-comments.js';
import type { AuthRequest } from '../types/auth.js';
import type { CreatePrReviewCommentResponse, PrReviewErrorResponse } from '../types/pr-review.js';
import { getDbManager } from '../middleware/db-middleware.js';

const router = Router();

/**
 * Zod schema for creating a PR review comment
 */
const CreateCommentSchema = z.object({
  githubCommentId: z.number().int().positive('githubCommentId must be a positive integer'),
  githubReviewId: z.number().int().positive('githubReviewId must be a positive integer'),
  githubPrNumber: z.number().int().positive('githubPrNumber must be a positive integer'),
  githubRepoOwner: z.string().min(1, 'githubRepoOwner is required'),
  githubRepoName: z.string().min(1, 'githubRepoName is required'),
  filePath: z.string().min(1, 'filePath is required'),
  lineNumber: z.number().int().positive().optional(),
  position: z.number().int().positive().optional(),
  impact: z.number().int().min(0).max(100).optional(),
  confidence: z.number().int().min(0).max(100).optional(),
  categories: z.array(z.string()).optional(),
  githubCommentUrl: z.string().url().optional(),
  githubReviewUrl: z.string().url().optional(),
});

/**
 * POST /api/pr-review/comments
 * Create a new PR review comment (called from CI)
 * Requires API key authentication
 */
router.post(
  '/comments',
  requireApiKey,
  async (
    req: AuthRequest,
    res: Response<CreatePrReviewCommentResponse | PrReviewErrorResponse>
  ) => {
    try {
      // Validate request body
      const parsed = CreateCommentSchema.safeParse(req.body);
      if (!parsed.success) {
        return res.status(400).json({
          error: 'Invalid request body',
          details: JSON.stringify(parsed.error.flatten()),
        });
      }

      const data = parsed.data;

      // Verify the tenant ID from API key matches the request
      if (!req.tenantId) {
        logger.warn('Tenant ID missing', {});
        return res.status(403).json({
          error: 'Tenant ID missing',
          details: 'The API key does not have an associated tenant ID',
        });
      }

      // Get database pool for the tenant
      const dbManager = getDbManager();
      const pool = await dbManager.get(req.tenantId);

      if (!pool) {
        logger.error(`Failed to get database pool for tenant: ${req.tenantId}`);
        return res.status(500).json({
          error: 'Database connection unavailable',
          details: 'Could not establish database connection for your organization',
        });
      }

      // Create the comment
      const comment = await createPrReviewComment(pool, data);

      if (!comment) {
        // Comment already exists
        return res.status(409).json({
          error: 'Comment already exists',
          details: `Comment with GitHub ID ${data.githubCommentId} already exists`,
        });
      }

      logger.info('PR review comment created', {
        tenantId: req.tenantId,
        commentId: comment.id,
        githubCommentId: comment.githubCommentId,
      });

      return res.status(201).json({
        success: true,
        comment,
      });
    } catch (error) {
      logger.error('Failed to create PR review comment', {
        error: error instanceof Error ? error.message : 'Unknown error',
        body: req.body,
      });

      return res.status(500).json({
        error: 'Failed to create PR review comment',
        details: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }
);

/**
 * GET /api/pr-review/comments/:owner/:repo/:prNumber
 * Get all comments for a PR with reaction counts
 * Requires admin authentication
 */
router.get(
  '/comments/:owner/:repo/:prNumber',
  requireAdmin,
  async (req: AuthRequest, res: Response) => {
    try {
      const tenantId = req.user?.tenantId;
      if (!tenantId) {
        return res.status(403).json({
          error: 'Tenant not found',
          details: 'User must belong to a provisioned tenant',
        });
      }

      const { owner, repo, prNumber } = req.params;

      // Validate required params
      if (!owner || !repo || !prNumber) {
        return res.status(400).json({
          error: 'Missing required parameters',
          details: 'owner, repo, and prNumber are required',
        });
      }

      // Validate PR number
      const prNum = parseInt(prNumber, 10);
      if (isNaN(prNum) || prNum <= 0) {
        return res.status(400).json({
          error: 'Invalid PR number',
          details: 'PR number must be a positive integer',
        });
      }

      // Check for database connection
      if (!req.db) {
        return res.status(500).json({
          error: 'Database connection unavailable',
          details: 'Could not establish database connection',
        });
      }

      // Get comments with reactions from tenant DB
      const comments = await getCommentsForPr(req.db, owner, repo, prNum);

      return res.json({
        comments,
        count: comments.length,
      });
    } catch (error) {
      logger.error('Failed to get PR comments', {
        error: error instanceof Error ? error.message : 'Unknown error',
        params: req.params,
        tenantId: req.user?.tenantId,
      });

      return res.status(500).json({
        error: 'Failed to get PR comments',
        details: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }
);

/**
 * GET /api/pr-review/analytics
 * Get reaction analytics for the authenticated tenant
 * Requires admin authentication
 */
router.get('/analytics', requireAdmin, async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(403).json({
        error: 'Tenant not found',
        details: 'User must belong to a provisioned tenant',
      });
    }

    // Parse limit query param
    const limitParam = req.query.limit;
    let limit = 10; // default

    if (limitParam) {
      const parsed = parseInt(limitParam as string, 10);
      if (isNaN(parsed) || parsed <= 0 || parsed > 100) {
        return res.status(400).json({
          error: 'Invalid limit parameter',
          details: 'Limit must be a positive integer between 1 and 100',
        });
      }
      limit = parsed;
    }

    // Check for database connection
    if (!req.db) {
      return res.status(500).json({
        error: 'Database connection unavailable',
        details: 'Could not establish database connection',
      });
    }

    // Get analytics from tenant DB
    const analytics = await getReactionAnalytics(req.db, limit);

    return res.json(analytics);
  } catch (error) {
    logger.error('Failed to get reaction analytics', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });

    return res.status(500).json({
      error: 'Failed to get reaction analytics',
      details: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

export { router as prReviewRouter };
