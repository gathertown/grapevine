import { memo, useEffect, useState } from 'react';
import type { FC } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';
import { billingApi } from '../../api/billing';
import { SectionHeader } from '../shared/SectionHeader';
import { SectionContainer } from '../shared/SectionContainer';
import type { BillingUsageResponse } from '../../types';
import { getTierName } from '../../utils/tierDefinitions';

interface UsageSectionProps {
  billingMode?: 'gather_managed' | 'grapevine_managed';
}

export const UsageSection: FC<UsageSectionProps> = memo(({ billingMode }) => {
  const [usage, setUsage] = useState<BillingUsageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUsage = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const usageData = await billingApi.getUsage();
        setUsage(usageData);
      } catch (err) {
        console.error('Failed to fetch usage data:', err);
        setError('Failed to load usage data');
      } finally {
        setIsLoading(false);
      }
    };

    fetchUsage();
  }, []);

  // Don't show usage section for gather-managed billing
  if (billingMode === 'gather_managed') {
    return null;
  }

  if (isLoading) {
    return (
      <Flex direction="column">
        <SectionHeader title="Usage" />
        <SectionContainer isComplete={false}>
          <Text color="tertiary">Loading usage information...</Text>
        </SectionContainer>
      </Flex>
    );
  }

  if (error || !usage) {
    return (
      <Flex direction="column">
        <SectionHeader title="Usage" />
        <SectionContainer isComplete={false}>
          <Text color="dangerPrimary">{error || 'Usage data not available'}</Text>
        </SectionContainer>
      </Flex>
    );
  }

  // Safely handle undefined values with defaults
  const requestsUsed = usage.requestsUsed ?? 0;
  const requestsAvailable = usage.requestsAvailable ?? 0;
  const usagePercentage = requestsAvailable > 0 ? (requestsUsed / requestsAvailable) * 100 : 0;

  return (
    <Flex direction="column">
      <SectionHeader title="Usage" />
      <SectionContainer isComplete={false}>
        <Flex direction="column" gap={16}>
          <Flex direction="row" align="center" justify="space-between">
            <Flex direction="column" gap={4}>
              <Text fontSize="md" fontWeight="semibold">
                Requests this period
              </Text>
              <Text fontSize="sm" color="tertiary">
                {getTierName(usage.tier)} plan
                {usage.isTrial && getTierName(usage.tier) !== 'Trial' && ' (Trial)'}
              </Text>
            </Flex>
            <Flex direction="column" align="flex-end" gap={4}>
              <Text fontSize="md" fontWeight="semibold">
                {requestsUsed.toLocaleString()} / {requestsAvailable.toLocaleString()}
              </Text>
              <Text fontSize="sm" color="tertiary">
                {Math.round(usagePercentage)}% used
              </Text>
            </Flex>
          </Flex>

          {/* Progress bar */}
          <Flex direction="column" gap={4}>
            <Flex
              width="100%"
              height="8px"
              borderRadius={4}
              backgroundColor="secondary"
              overflow="hidden"
            >
              <Flex
                width={`${Math.min(usagePercentage, 100)}%`}
                height="100%"
                backgroundColor={usagePercentage >= 90 ? 'dangerPrimary' : 'accentPrimary'}
              />
            </Flex>
          </Flex>

          {usagePercentage >= 90 && (
            <Flex
              py={8}
              px={12}
              backgroundColor="dangerTertiary"
              borderRadius={4}
              borderColor="dangerPrimary"
              borderWidth={1}
              borderStyle="solid"
            >
              <Text fontSize="sm" color="dangerPrimary">
                You're approaching your usage limit. Consider upgrading your plan to avoid service
                interruption.
              </Text>
            </Flex>
          )}
        </Flex>
      </SectionContainer>
    </Flex>
  );
});

UsageSection.displayName = 'UsageSection';
