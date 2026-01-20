/**
 * API client for PR Review endpoints
 */
import { apiClient } from './client';

/**
 * PR Review Comment with aggregated reaction counts
 */
export interface PrReviewCommentWithReactions {
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
 * Reaction analytics for a tenant's PR review comments
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

const API_BASE = '/api/pr-review';

export const prReviewApi = {
  /**
   * Get reaction analytics for the authenticated tenant
   */
  async getAnalytics(limit: number = 10): Promise<ReactionAnalytics> {
    const params = new URLSearchParams();
    if (limit !== 10) {
      params.set('limit', limit.toString());
    }
    const url = `${API_BASE}/analytics${params.toString() ? `?${params.toString()}` : ''}`;
    return await apiClient.get<ReactionAnalytics>(url);
  },
};
