import { memo, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text, Button } from '@gathertown/gather-design-system';
import type { TrialStatus, SubscriptionStatus } from '../../types';
import { TrialSection } from './TrialSection';
import { SectionHeader } from '../shared/SectionHeader';
import { SectionContainer } from '../shared/SectionContainer';
import { getTierName, getTierPrice } from '../../utils/tierDefinitions';
import { billingApi } from '../../api/billing';

interface PlanSummarySectionProps {
  trial: TrialStatus;
  subscription: SubscriptionStatus;
  showInline?: boolean; // When true, shows as inline content (for HomePage), when false shows as full section (for billing page)
}

export const PlanSummarySection: FC<PlanSummarySectionProps> = memo(
  ({ trial, subscription, showInline = false }) => {
    const navigate = useNavigate();
    const [isProcessing, setIsProcessing] = useState(false);

    const handleButtonClick = async () => {
      if (showInline) {
        // On home page, navigate to billing
        navigate('/billing');
      } else {
        // On billing page, open Stripe portal
        try {
          setIsProcessing(true);
          const response = await billingApi.getPortalSession();
          if (response && response.url) {
            window.location.href = response.url;
          }
        } catch (err) {
          console.error('Failed to open portal:', err);
        } finally {
          setIsProcessing(false);
        }
      }
    };

    // If we have an active subscription, show plan details
    if (subscription.hasActiveSubscription) {
      const { plan, currentPeriodEnd, cancelAtPeriodEnd } = subscription;
      const tierInfo = getTierPrice(plan || 'team');

      const content = (
        <Flex direction="row" align="center" justify="space-between">
          <Flex direction="column" gap={4}>
            <Text fontSize="md" fontWeight="semibold">
              {getTierName(plan || 'team')}
            </Text>
            {!cancelAtPeriodEnd && (
              <Flex direction="row" align="baseline">
                <Text fontSize="sm" color="tertiary">
                  {tierInfo.price}
                </Text>
                {tierInfo.period && (
                  <Text fontSize="sm" color="tertiary">
                    {tierInfo.period}
                  </Text>
                )}
              </Flex>
            )}
            {cancelAtPeriodEnd && currentPeriodEnd && (
              <Text fontSize="sm" color="tertiary">
                Cancelled
              </Text>
            )}
          </Flex>
          {showInline && (
            <Button kind="secondary" onClick={handleButtonClick} disabled={isProcessing}>
              {isProcessing ? 'Loading...' : 'Manage billing'}
            </Button>
          )}
        </Flex>
      );

      if (showInline) {
        return (
          <Flex direction="column" justify="space-between" gap={16} p={16}>
            {content}
          </Flex>
        );
      }

      return (
        <Flex direction="column">
          <SectionHeader title="Current plan" />
          <SectionContainer isComplete={false}>{content}</SectionContainer>
        </Flex>
      );
    }

    // If we're in trial, delegate to TrialSection
    if (trial.isInTrial) {
      return <TrialSection trial={trial} subscription={subscription} showInline={showInline} />;
    }

    // Default fallback - delegate to TrialSection which handles non-trial states
    return <TrialSection trial={trial} subscription={subscription} showInline={showInline} />;
  }
);

PlanSummarySection.displayName = 'PlanSummarySection';
