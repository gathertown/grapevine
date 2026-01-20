import { memo } from 'react';
import type { FC } from 'react';
import { Flex, Box, Text, Badge } from '@gathertown/gather-design-system';
import type { StatsSummary } from '../api/stats';

interface SplitStatisticsProps {
  summary: StatsSummary;
}

const SplitStatistics: FC<SplitStatisticsProps> = memo(({ summary }) => {
  // Calculate percentages for messages
  const totalMessages = summary.totalMessages;
  const channelPercentage = totalMessages > 0 ? (summary.channelMessages / totalMessages) * 100 : 0;
  const dmPercentage = totalMessages > 0 ? (summary.dmMessages / totalMessages) * 100 : 0;

  // Calculate percentages for reactions
  const totalReactions = summary.totalReactions;
  const positivePercentage =
    totalReactions > 0 ? (summary.positiveReactions / totalReactions) * 100 : 0;
  const negativePercentage =
    totalReactions > 0 ? (summary.negativeReactions / totalReactions) * 100 : 0;
  const neutralPercentage = 100 - positivePercentage - negativePercentage;

  // Calculate percentages for button feedback
  const totalButtonFeedback = summary.totalButtonFeedback || 0;
  const positiveButtonPercentage =
    totalButtonFeedback > 0 ? (summary.positiveButtonFeedback / totalButtonFeedback) * 100 : 0;
  const negativeButtonPercentage =
    totalButtonFeedback > 0 ? (summary.negativeButtonFeedback / totalButtonFeedback) * 100 : 0;

  return (
    <Flex direction="row" gap={24} flexWrap="wrap">
      {/* Messages Split */}
      <Box
        backgroundColor="primary"
        p={24}
        borderRadius={12}
        borderWidth={1}
        borderStyle="solid"
        borderColor="tertiary"
        style={{
          flex: '1',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
          transition: 'all 0.2s ease',
        }} //TODO use GDC Flex and shadow tokens
      >
        <Flex
          justify="space-between"
          align="center"
          mb={20}
          pb={12}
          style={{ borderBottom: '2px solid #f8f9fa' }} // TODO: use GDC border
        >
          <Text fontSize="lg" fontWeight="semibold" color="primary">
            Messages by Location
          </Text>
          <Badge color="gray" text={`${totalMessages.toLocaleString()} total`} />
        </Flex>

        <Flex direction="column" gap={16}>
          <Flex direction="column" gap={8}>
            <Flex align="center" gap={8}>
              <Box // TODO: use GDC Flex and font tokens
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  background: '#e3f2fd',
                  color: '#1565c0',
                }}
              >
                #
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Channels
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #2196f3 0%, #1976d2 100%)',
                  transition: 'all 0.3s ease',
                  width: `${channelPercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {summary.channelMessages.toLocaleString()}
              </Text>
              <Badge color="gray" text={`${channelPercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>

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
                  fontWeight: '600',
                  background: '#f3e5f5',
                  color: '#7b1fa2',
                }}
              >
                💬
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Direct Messages
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #9c27b0 0%, #7b1fa2 100%)',
                  transition: 'all 0.3s ease',
                  width: `${dmPercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {summary.dmMessages.toLocaleString()}
              </Text>
              <Badge color="gray" text={`${dmPercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>
        </Flex>
      </Box>

      {/* Reactions Split */}
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
          transition: 'all 0.2s ease',
        }}
      >
        <Flex
          justify="space-between"
          align="center"
          style={{ marginBottom: '20px', paddingBottom: '12px', borderBottom: '2px solid #f8f9fa' }}
        >
          <Text fontSize="lg" fontWeight="semibold" color="primary">
            Reactions by Sentiment
          </Text>
          <Badge color="gray" text={`${totalReactions.toLocaleString()} total`} />
        </Flex>

        <Flex direction="column" gap={16}>
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
                  fontWeight: '600',
                  background: '#e8f5e8',
                  color: '#2e7d32',
                }}
              >
                👍
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Positive
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #4caf50 0%, #2e7d32 100%)',
                  transition: 'all 0.3s ease',
                  width: `${positivePercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {summary.positiveReactions.toLocaleString()}
              </Text>
              <Badge color="gray" text={`${positivePercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>

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
                  fontWeight: '600',
                  background: '#ffebee',
                  color: '#c62828',
                }}
              >
                👎
              </Box>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Negative
              </Text>
            </Flex>
            <Box
              style={{
                height: '8px',
                background: '#f1f3f4',
                borderRadius: '4px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <Box
                style={{
                  height: '100%',
                  borderRadius: '4px',
                  background: 'linear-gradient(90deg, #f44336 0%, #c62828 100%)',
                  transition: 'all 0.3s ease',
                  width: `${negativePercentage}%`,
                }}
              />
            </Box>
            <Flex justify="space-between" align="center">
              <Text fontSize="lg" fontWeight="bold" color="primary">
                {summary.negativeReactions.toLocaleString()}
              </Text>
              <Badge color="gray" text={`${negativePercentage.toFixed(1)}%`} />
            </Flex>
          </Flex>

          {neutralPercentage > 0 && (
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
                    fontWeight: '600',
                    background: '#f5f5f5',
                    color: '#757575',
                  }}
                >
                  😐
                </Box>
                <Text fontSize="sm" fontWeight="medium" color="primary">
                  Neutral
                </Text>
              </Flex>
              <Box
                style={{
                  height: '8px',
                  background: '#f1f3f4',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <Box
                  style={{
                    height: '100%',
                    borderRadius: '4px',
                    background: 'linear-gradient(90deg, #9e9e9e 0%, #757575 100%)',
                    transition: 'all 0.3s ease',
                    width: `${neutralPercentage}%`,
                  }}
                />
              </Box>
              <Flex justify="space-between" align="center">
                <Text fontSize="lg" fontWeight="bold" color="primary">
                  {(
                    totalReactions -
                    summary.positiveReactions -
                    summary.negativeReactions
                  ).toLocaleString()}
                </Text>
                <Badge color="gray" text={`${neutralPercentage.toFixed(1)}%`} />
              </Flex>
            </Flex>
          )}
        </Flex>
      </Box>

      {/* Button Feedback Split - Only show when there's data */}
      {totalButtonFeedback > 0 && (
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
            transition: 'all 0.2s ease',
          }}
        >
          <Flex
            justify="space-between"
            align="center"
            style={{
              marginBottom: '20px',
              paddingBottom: '12px',
              borderBottom: '2px solid #f8f9fa',
            }}
          >
            <Text fontSize="lg" fontWeight="semibold" color="primary">
              Button Feedback
            </Text>
            <Badge color="gray" text={`${totalButtonFeedback.toLocaleString()} total`} />
          </Flex>

          <Flex direction="column" gap={16}>
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
                    fontWeight: '600',
                    background: '#e8f5e8',
                    color: '#2e7d32',
                  }}
                >
                  👍
                </Box>
                <Text fontSize="sm" fontWeight="medium" color="primary">
                  Helpful
                </Text>
              </Flex>
              <Box
                style={{
                  height: '8px',
                  background: '#f1f3f4',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <Box
                  style={{
                    height: '100%',
                    borderRadius: '4px',
                    background: 'linear-gradient(90deg, #4caf50 0%, #2e7d32 100%)',
                    transition: 'all 0.3s ease',
                    width: `${positiveButtonPercentage}%`,
                  }}
                />
              </Box>
              <Flex justify="space-between" align="center">
                <Text fontSize="lg" fontWeight="bold" color="primary">
                  {(summary.positiveButtonFeedback || 0).toLocaleString()}
                </Text>
                <Badge color="gray" text={`${positiveButtonPercentage.toFixed(1)}%`} />
              </Flex>
            </Flex>

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
                    fontWeight: '600',
                    background: '#ffebee',
                    color: '#c62828',
                  }}
                >
                  👎
                </Box>
                <Text fontSize="sm" fontWeight="medium" color="primary">
                  Not Helpful
                </Text>
              </Flex>
              <Box
                style={{
                  height: '8px',
                  background: '#f1f3f4',
                  borderRadius: '4px',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <Box
                  style={{
                    height: '100%',
                    borderRadius: '4px',
                    background: 'linear-gradient(90deg, #f44336 0%, #c62828 100%)',
                    transition: 'all 0.3s ease',
                    width: `${negativeButtonPercentage}%`,
                  }}
                />
              </Box>
              <Flex justify="space-between" align="center">
                <Text fontSize="lg" fontWeight="bold" color="primary">
                  {(summary.negativeButtonFeedback || 0).toLocaleString()}
                </Text>
                <Badge color="gray" text={`${negativeButtonPercentage.toFixed(1)}%`} />
              </Flex>
            </Flex>
          </Flex>
        </Box>
      )}
    </Flex>
  );
});

SplitStatistics.displayName = 'SplitStatistics';

export { SplitStatistics };
