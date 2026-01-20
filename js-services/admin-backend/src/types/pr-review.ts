/**
 * PR Review Types
 *
 * TypeScript interfaces for PR review comments and reactions tracking
 */

/**
 * PR Review Comment - stored in tenant database
 * Represents a single comment from Grapevine's automated PR review
 */
export interface PrReviewComment {
  id: string;
  githubCommentId: number;
  githubReviewId: number;
  githubPrNumber: number;
  githubRepoOwner: string;
  githubRepoName: string;
  filePath: string;
  lineNumber: number | null;
  position: number | null;
  impact: number | null;
  confidence: number | null;
  categories: string[] | null;
  githubCommentUrl: string | null;
  githubReviewUrl: string | null;
  lastSyncedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * GitHub reaction types
 * Maps to GitHub API reaction content values:
 * - +1 -> thumbs_up
 * - -1 -> thumbs_down
 * - laugh -> laugh
 * - confused -> confused
 * - heart -> heart
 * - hooray -> hooray
 * - rocket -> rocket
 * - eyes -> eyes
 */
export type GitHubReactionType =
  | 'thumbs_up'
  | 'thumbs_down'
  | 'laugh'
  | 'confused'
  | 'heart'
  | 'hooray'
  | 'rocket'
  | 'eyes';

/**
 * PR Review Comment Reaction - stored in tenant database
 * Represents a reaction synced from GitHub
 */
export interface PrReviewCommentReaction {
  id: string;
  commentId: string;
  githubUsername: string;
  reactionType: GitHubReactionType;
  syncedAt: string;
  createdAt: string;
  updatedAt: string;
}

/**
 * PR Review Comment with aggregated reaction counts
 * Used for API responses
 */
export interface PrReviewCommentWithReactions extends PrReviewComment {
  reactions: {
    thumbsUpCount: number;
    thumbsDownCount: number;
    laughCount: number;
    confusedCount: number;
    heartCount: number;
    hoorayCount: number;
    rocketCount: number;
    eyesCount: number;
    totalCount: number;
  };
}

/**
 * Request body for creating a PR review comment
 * Called from CI after posting review to GitHub
 */
export interface CreatePrReviewCommentRequest {
  tenantId: string;
  githubCommentId: number;
  githubReviewId: number;
  githubPrNumber: number;
  githubRepoOwner: string;
  githubRepoName: string;
  filePath: string;
  lineNumber?: number;
  position?: number;
  impact?: number;
  confidence?: number;
  categories?: string[];
  githubCommentUrl?: string;
  githubReviewUrl?: string;
}

/**
 * Response for creating a PR review comment
 */
export interface CreatePrReviewCommentResponse {
  success: boolean;
  comment: PrReviewComment;
}

/**
 * Reaction analytics for a tenant's comments
 */
export interface ReactionAnalytics {
  totalComments: number;
  totalReactions: number;
  thumbsUpTotal: number;
  thumbsDownTotal: number;
  laughTotal: number;
  confusedTotal: number;
  heartTotal: number;
  hoorayTotal: number;
  rocketTotal: number;
  eyesTotal: number;
  avgReactionsPerComment: number;
  /** Number of comments where thumbs_up > thumbs_down */
  netPositiveComments: number;
  /** Number of comments where thumbs_down > thumbs_up */
  netNegativeComments: number;
  topReactedComments: Array<{
    comment: PrReviewCommentWithReactions;
    reactionScore: number; // thumbs_up - thumbs_down
  }>;
  bottomReactedComments: Array<{
    comment: PrReviewCommentWithReactions;
    reactionScore: number; // thumbs_up - thumbs_down
  }>;
}

/**
 * Error response for PR review endpoints
 */
export interface PrReviewErrorResponse {
  error: string;
  details?: string;
}
