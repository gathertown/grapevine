import { memo, useState, useEffect, useCallback } from 'react';
import type { FC } from 'react';
import { Flex, Box, Text, Badge, Button, Icon } from '@gathertown/gather-design-system';
import {
  prReviewApi,
  type ReactionAnalytics,
  type PrReviewCommentWithReactions,
} from '../api/pr-review';

/**
 * Statistics card for displaying reaction summary
 */
const ReactionStatsCard: FC<{ analytics: ReactionAnalytics }> = memo(({ analytics }) => {
  // Calculate net positive/negative percentages based on total comments
  const netPositivePercentage =
    analytics.totalComments > 0
      ? (analytics.netPositiveComments / analytics.totalComments) * 100
      : 0;
  const netNegativePercentage =
    analytics.totalComments > 0
      ? (analytics.netNegativeComments / analytics.totalComments) * 100
      : 0;

  return (
    <Flex direction="row" gap={24} flexWrap="wrap">
      {/* Overview Stats */}
      <Box
        backgroundColor="primary"
        p={24}
        borderRadius={12}
        borderWidth={1}
        borderStyle="solid"
        borderColor="tertiary"
        style={{
          flex: '1',
          minWidth: '280px',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Flex
          justify="space-between"
          align="center"
          mb={20}
          pb={12}
          style={{ borderBottom: '2px solid #f8f9fa' }}
        >
          <Text fontSize="lg" fontWeight="semibold" color="primary">
            Overview
          </Text>
        </Flex>

        <Flex direction="column" gap={16}>
          <Flex direction="column" gap={4}>
            <Text fontSize="sm" color="tertiary">
              Total Comments
            </Text>
            <Text fontSize="xl" fontWeight="bold" color="primary">
              {analytics.totalComments.toLocaleString()}
            </Text>
          </Flex>

          <Flex direction="column" gap={4}>
            <Text fontSize="sm" color="tertiary">
              Total Reactions
            </Text>
            <Text fontSize="xl" fontWeight="bold" color="primary">
              {analytics.totalReactions.toLocaleString()}
            </Text>
          </Flex>

          <Flex direction="column" gap={4}>
            <Text fontSize="sm" color="tertiary">
              Avg. Reactions per Comment
            </Text>
            <Text fontSize="xl" fontWeight="bold" color="primary">
              {analytics.avgReactionsPerComment.toFixed(2)}
            </Text>
          </Flex>
        </Flex>
      </Box>

      {/* Comment Sentiment (Net Positive/Negative) */}
      <Box
        backgroundColor="primary"
        p={24}
        borderRadius={12}
        borderWidth={1}
        borderStyle="solid"
        borderColor="tertiary"
        style={{
          flex: '1',
          minWidth: '400px',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Flex
          justify="space-between"
          align="center"
          mb={20}
          pb={12}
          style={{ borderBottom: '2px solid #f8f9fa' }}
        >
          <Text fontSize="lg" fontWeight="semibold" color="primary">
            Comment Sentiment
          </Text>
          <Badge color="gray" text={`${analytics.totalComments.toLocaleString()} comments`} />
        </Flex>

        <Flex direction="column" gap={16}>
          {/* Net Positive Comments */}
          <Flex direction="column" gap={8}>
            <Flex align="center" gap={8}>
              <Box
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  background: '#e8f5e8',
                  color: '#2e7d32',
                }}
              >
                👍
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Net Positive
              </Text>
              <Text fontSize="xs" color="tertiary">
                (👍 &gt; 👎)
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #4caf50 0%, #2e7d32 100%)',
                  transition: 'all 0.3s ease',
                  width: `${netPositivePercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {analytics.netPositiveComments.toLocaleString()} comments
              </Text>
              <Badge color="gray" text={`${netPositivePercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>

          {/* Net Negative Comments */}
          <Flex direction="column" gap={8}>
            <Flex align="center" gap={8}>
              <Box
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  background: '#ffebee',
                  color: '#c62828',
                }}
              >
                👎
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Net Negative
              </Text>
              <Text fontSize="xs" color="tertiary">
                (👎 &gt; 👍)
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #f44336 0%, #c62828 100%)',
                  transition: 'all 0.3s ease',
                  width: `${netNegativePercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {analytics.netNegativeComments.toLocaleString()} comments
              </Text>
              <Badge color="gray" text={`${netNegativePercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>
        </Flex>
      </Box>

      {/* All Reactions Breakdown */}
      <Box
        backgroundColor="primary"
        p={24}
        borderRadius={12}
        borderWidth={1}
        borderStyle="solid"
        borderColor="tertiary"
        style={{
          flex: '1',
          minWidth: '280px',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Flex
          justify="space-between"
          align="center"
          mb={20}
          pb={12}
          style={{ borderBottom: '2px solid #f8f9fa' }}
        >
          <Text fontSize="lg" fontWeight="semibold" color="primary">
            All Reactions
          </Text>
        </Flex>

        <Flex direction="column" gap={8}>
          <Flex justify="space-between">
            <Text fontSize="sm">👍 Thumbs Up</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.thumbsUpTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">👎 Thumbs Down</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.thumbsDownTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">😄 Laugh</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.laughTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">😕 Confused</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.confusedTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">❤️ Heart</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.heartTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">🎉 Hooray</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.hoorayTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">🚀 Rocket</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.rocketTotal}
            </Text>
          </Flex>
          <Flex justify="space-between">
            <Text fontSize="sm">👀 Eyes</Text>
            <Text fontSize="sm" fontWeight="semibold">
              {analytics.eyesTotal}
            </Text>
          </Flex>
        </Flex>
      </Box>
    </Flex>
  );
});

ReactionStatsCard.displayName = 'ReactionStatsCard';

/**
 * Individual comment card
 */
const CommentCard: FC<{
  comment: PrReviewCommentWithReactions;
  reactionScore: number;
}> = memo(({ comment, reactionScore }) => {
  const prUrl = `https://github.com/${comment.githubRepoOwner}/${comment.githubRepoName}/pull/${comment.githubPrNumber}`;
  const commentUrl = comment.githubCommentUrl || prUrl;

  // Determine sentiment styling
  const getSentimentStyle = () => {
    if (reactionScore > 0) return { borderLeft: '4px solid #4caf50' };
    if (reactionScore < 0) return { borderLeft: '4px solid #f44336' };
    return { borderLeft: '4px solid #9e9e9e' };
  };

  return (
    <Box
      backgroundColor="primary"
      p={16}
      borderRadius={8}
      style={{
        ...getSentimentStyle(),
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
      }}
    >
      <Flex direction="column" gap={12}>
        {/* Header */}
        <Flex justify="space-between" align="flex-start" gap={16}>
          <Flex direction="column" gap={4} style={{ flex: 1 }}>
            <Flex align="center" gap={8}>
              <a
                href={prUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ textDecoration: 'none', color: 'var(--color-accent)' }}
              >
                <Text fontSize="sm" fontWeight="semibold">
                  {comment.githubRepoOwner}/{comment.githubRepoName}#{comment.githubPrNumber}
                </Text>
              </a>
              <Icon name="arrowUpRight" size="xs" color="tertiary" />
            </Flex>
            <Flex style={{ wordBreak: 'break-all' }}>
              <Text fontSize="xs" color="tertiary">
                {comment.filePath}
                {comment.lineNumber && `:${comment.lineNumber}`}
              </Text>
            </Flex>
          </Flex>

          <Flex align="center" gap={8}>
            {comment.impact !== null && (
              <Badge
                color={comment.impact >= 70 ? 'danger' : comment.impact >= 40 ? 'warning' : 'gray'}
                text={`Impact: ${comment.impact}`}
              />
            )}
            {comment.confidence !== null && (
              <Badge color="gray" text={`Conf: ${comment.confidence}`} />
            )}
          </Flex>
        </Flex>

        {/* Categories */}
        {comment.categories && comment.categories.length > 0 && (
          <Flex gap={4} flexWrap="wrap">
            {comment.categories.map((category, idx) => (
              <Badge key={idx} color="accent" text={category} />
            ))}
          </Flex>
        )}

        {/* Reactions */}
        <Flex justify="space-between" align="center">
          <Flex gap={12}>
            <Flex align="center" gap={4}>
              <Text fontSize="sm">👍</Text>
              <Text fontSize="sm" fontWeight="medium">
                {comment.reactions.thumbsUpCount}
              </Text>
            </Flex>
            <Flex align="center" gap={4}>
              <Text fontSize="sm">👎</Text>
              <Text fontSize="sm" fontWeight="medium">
                {comment.reactions.thumbsDownCount}
              </Text>
            </Flex>
            {comment.reactions.totalCount >
              comment.reactions.thumbsUpCount + comment.reactions.thumbsDownCount && (
              <Flex align="center" gap={4}>
                <Text fontSize="sm" color="tertiary">
                  +
                  {comment.reactions.totalCount -
                    comment.reactions.thumbsUpCount -
                    comment.reactions.thumbsDownCount}{' '}
                  others
                </Text>
              </Flex>
            )}
          </Flex>

          <Flex align="center" gap={8}>
            <Text fontSize="xs" color="tertiary">
              Score: {reactionScore >= 0 ? '+' : ''}
              {reactionScore}
            </Text>
            <a
              href={commentUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: 'none' }}
            >
              <Button kind="secondary" size="sm">
                View on GitHub
              </Button>
            </a>
          </Flex>
        </Flex>
      </Flex>
    </Box>
  );
});

CommentCard.displayName = 'CommentCard';

/**
 * Comments list section
 */
const CommentsSection: FC<{
  title: string;
  comments: Array<{ comment: PrReviewCommentWithReactions; reactionScore: number }>;
  emptyMessage: string;
}> = memo(({ title, comments, emptyMessage }) => {
  return (
    <Box backgroundColor="primary" borderRadius={8} overflow="hidden">
      <Flex
        p={16}
        px={20}
        backgroundColor="secondary"
        direction="row"
        justify="space-between"
        align="center"
      >
        <Text fontSize="lg" fontWeight="semibold">
          {title}
        </Text>
        <Badge color="gray" text={`${comments.length} comments`} />
      </Flex>

      <Flex direction="column" p={20} gap={12}>
        {comments.length === 0 ? (
          <Flex align="center" justify="center" p={24}>
            <Text fontSize="md" color="tertiary">
              {emptyMessage}
            </Text>
          </Flex>
        ) : (
          comments.map(({ comment, reactionScore }) => (
            <CommentCard key={comment.id} comment={comment} reactionScore={reactionScore} />
          ))
        )}
      </Flex>
    </Box>
  );
});

CommentsSection.displayName = 'CommentsSection';

/**
 * Main page component
 */
const ReviewerFeedbackPage: FC = memo(() => {
  const [analytics, setAnalytics] = useState<ReactionAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await prReviewApi.getAnalytics(10);
      setAnalytics(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load analytics';
      setError(errorMessage);
      console.error('Error loading reviewer analytics:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <Flex
        direction="column"
        align="center"
        justify="center"
        p={32}
        backgroundColor="primary"
        borderRadius={8}
        maxWidth={1200}
        minHeight="50vh"
      >
        <Text fontSize="lg">Loading reviewer feedback...</Text>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex
        direction="column"
        align="center"
        justify="center"
        p={32}
        backgroundColor="primary"
        borderRadius={8}
        maxWidth={1200}
        minHeight="50vh"
        gap={16}
      >
        <Text fontSize="xl" fontWeight="semibold">
          Error Loading Feedback
        </Text>
        <Text fontSize="md" color="tertiary">
          {error}
        </Text>
        <Button onClick={loadData} kind="primary">
          Try Again
        </Button>
      </Flex>
    );
  }

  if (!analytics) {
    return null;
  }

  return (
    <Flex direction="column" maxWidth={1200} gap={24}>
      {/* Stats Summary */}
      <ReactionStatsCard analytics={analytics} />

      {/* Top Reacted Comments */}
      <CommentsSection
        title="Top Rated Comments"
        comments={analytics.topReactedComments}
        emptyMessage="No comments with reactions yet."
      />

      {/* Bottom Reacted Comments */}
      <CommentsSection
        title="Lowest Rated Comments"
        comments={analytics.bottomReactedComments}
        emptyMessage="No comments with negative feedback yet."
      />
    </Flex>
  );
});

ReviewerFeedbackPage.displayName = 'ReviewerFeedbackPage';

export { ReviewerFeedbackPage };
