import { memo, useState } from 'react';
import type { FC } from 'react';
import { useBillingStatus } from '../../hooks/useBillingStatus';
import { billingApi } from '../../api/billing';
import { Box, Button, Flex, Text, Icon } from '@gathertown/gather-design-system';
import { PlanSummarySection } from './PlanSummarySection';
import { UsageSection } from './UsageSection';
import { BillingCancelModal } from './BillingCancelModal';
import { SectionHeader } from '../shared/SectionHeader';
import { SectionContainer } from '../shared/SectionContainer';
import { getEffectiveEndDate, formatEndDate } from '../../utils/billingUtils';
import type { SubscriptionStatus } from '../../types';

const BillingPage: FC = memo(() => {
  const { billingStatus, isLoading, error, refetch, pollUntilChange } = useBillingStatus();
  const [isProcessing, setIsProcessing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  const handleCancelSubscription = async () => {
    if (!billingStatus?.subscription.hasActiveSubscription) return;

    try {
      setIsProcessing(true);
      setIsCancelModalOpen(false);
      setSyncMessage('Cancelling subscription...');

      await billingApi.cancelSubscription();
      setSyncMessage('Waiting for confirmation...');

      // Poll until we see the cancellation reflected in the backend
      const confirmed = await pollUntilChange(
        (status) => status.subscription.cancelAtPeriodEnd === true,
        12000 // 12 seconds
      );

      if (!confirmed) {
        setSyncMessage(
          "Cancellation successful, but sync is taking longer than expected. Try refreshing if status doesn't update."
        );
        setTimeout(() => setSyncMessage(null), 5000);
      } else {
        setSyncMessage(null);
      }
    } catch (err) {
      console.error('Failed to cancel subscription:', err);
      setSyncMessage('Failed to cancel subscription. Please try again.');
      setTimeout(() => setSyncMessage(null), 3000);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleOpenCancelModal = () => {
    setIsCancelModalOpen(true);
  };

  const handleCloseCancelModal = () => {
    setIsCancelModalOpen(false);
  };

  const handleReactivateSubscription = async () => {
    if (!billingStatus?.subscription.hasActiveSubscription) return;

    try {
      setIsProcessing(true);
      setSyncMessage('Reactivating subscription...');

      await billingApi.reactivateSubscription();
      setSyncMessage('Waiting for confirmation...');

      // Poll until we see the reactivation reflected in the backend
      const confirmed = await pollUntilChange(
        (status) => status.subscription.cancelAtPeriodEnd === false,
        12000 // 12 seconds
      );

      if (!confirmed) {
        setSyncMessage(
          "Reactivation successful, but sync is taking longer than expected. Try refreshing if status doesn't update."
        );
        setTimeout(() => setSyncMessage(null), 5000);
      } else {
        setSyncMessage(null);
      }
    } catch (err) {
      console.error('Failed to reactivate subscription:', err);
      setSyncMessage('Failed to reactivate subscription. Please try again.');
      setTimeout(() => setSyncMessage(null), 3000);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleOpenPortal = async () => {
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
  };

  if (isLoading) {
    return (
      <Flex width="100%" direction="column">
        <SectionContainer>
          <Text color="tertiary">Loading billing information...</Text>
        </SectionContainer>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex width="100%" direction="column">
        <SectionContainer>
          <Flex direction="row" justify="space-between" align="center" gap={16}>
            <Text color="dangerPrimary">Error loading billing information</Text>
            <Button onClick={refetch} kind="secondary">
              Try Again
            </Button>
          </Flex>
        </SectionContainer>
      </Flex>
    );
  }

  if (!billingStatus) {
    return (
      <Flex width="100%" direction="column">
        <SectionContainer>
          <Text color="tertiary">No billing information available.</Text>
        </SectionContainer>
      </Flex>
    );
  }

  const { trial, subscription, billingMode } = billingStatus;

  // For gather_managed billing mode, show different UI
  if (billingMode === 'gather_managed') {
    return (
      <Flex width="100%" direction="column" gap={32}>
        <SectionContainer>
          <Flex direction="column" gap={16}>
            <Text fontSize="lg" fontWeight="semibold">
              Billing managed by Gather
            </Text>
            <Text color="tertiary">
              Your billing is managed externally by Gather. For billing questions or changes, please
              contact your Gather administrator.
            </Text>
          </Flex>
        </SectionContainer>
      </Flex>
    );
  }

  // For enterprise plans, show custom enterprise UI
  if (subscription.plan === 'enterprise') {
    return (
      <Flex width="100%" direction="column" gap={32}>
        {/* Enterprise Plan Banner */}
        <SectionContainer>
          <Flex direction="column" gap={16}>
            <Text fontSize="lg" fontWeight="semibold">
              Custom Enterprise Plan
            </Text>
            <Text color="tertiary">
              Your billing is a custom plan. For billing questions or changes, please contact your
              account executive.
            </Text>
          </Flex>
        </SectionContainer>

        {/* Usage Section - only show if flag is enabled */}
        {billingStatus.enableBillingUsageUI && <UsageSection billingMode={billingMode} />}
      </Flex>
    );
  }

  return (
    <Flex width="100%" direction="column" gap={32}>
      {/* Plan Summary Section */}
      <PlanSummarySection trial={trial} subscription={subscription} showInline={false} />

      {/* Usage Section */}
      {billingStatus.enableBillingUsageUI && <UsageSection billingMode={billingMode} />}

      {/* Payment & Billing Section */}
      {subscription.hasActiveSubscription && (
        <Flex direction="column">
          <SectionHeader title="Edit payment method"></SectionHeader>
          <SectionContainer isComplete={false}>
            <Flex direction="row" align="center" justify="space-between">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Payment & billing
                </Text>

                <Text fontSize="sm" color="tertiary">
                  Update your payment information, change plan, or download invoices in our secure
                  Stripe portal.
                </Text>
              </Flex>
              <Button onClick={handleOpenPortal} kind="secondary" disabled={isProcessing}>
                {isProcessing ? (
                  'Loading...'
                ) : (
                  <Flex direction="row" align="center" gap={4}>
                    <span>Stripe portal</span>
                    <Icon name="arrowUpRight" size="sm" />
                  </Flex>
                )}
              </Button>
            </Flex>
          </SectionContainer>
        </Flex>
      )}

      {/* Cancel/Reactivate Plan Section */}
      {subscription.hasActiveSubscription && (
        <Flex direction="column">
          <SectionHeader
            title={subscription.cancelAtPeriodEnd ? 'Reactivate plan' : 'Cancel plan'}
          />
          <SectionContainer isComplete={false}>
            <Flex direction="row" align="center" justify="space-between">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  {subscription.cancelAtPeriodEnd && subscription.currentPeriodEnd
                    ? 'Reactivate your Grapevine plan'
                    : 'Cancel your Grapevine plan'}
                </Text>
                <Text fontSize="sm" color="tertiary">
                  {subscription.cancelAtPeriodEnd ? (
                    getCancellationMessage(subscription)
                  ) : subscription.status === 'trialing' && subscription.trialEnd ? (
                    <>
                      Your free trial ends on{' '}
                      <Text as="span">{formatEndDate(subscription.trialEnd)}</Text>
                    </>
                  ) : subscription.currentPeriodEnd ? (
                    <>
                      Renews <Text as="span">{formatEndDate(subscription.currentPeriodEnd)}</Text>
                    </>
                  ) : (
                    'You can cancel your plan. It will remain active until the end of the billing period.'
                  )}
                </Text>
              </Flex>
              {subscription.cancelAtPeriodEnd ? (
                <Button
                  onClick={handleReactivateSubscription}
                  kind="primary"
                  disabled={isProcessing}
                >
                  {isProcessing ? 'Loading...' : 'Reactivate plan'}
                </Button>
              ) : (
                <Button
                  onClick={handleOpenCancelModal}
                  kind="dangerSecondary"
                  disabled={isProcessing}
                >
                  {isProcessing ? 'Loading...' : 'Cancel plan'}
                </Button>
              )}
            </Flex>
          </SectionContainer>
        </Flex>
      )}

      {/* Sync message display */}
      {syncMessage && (
        <Box
          py={16}
          backgroundColor="accentTertiary"
          borderColor="accentTertiary"
          borderWidth={1}
          borderStyle="solid"
          borderRadius={6}
          px={16}
          my={16}
        >
          <Text color="secondary" fontSize="xs">
            {syncMessage}
          </Text>
        </Box>
      )}

      {/* Cancel Confirmation Modal */}
      <BillingCancelModal
        isOpen={isCancelModalOpen}
        onClose={handleCloseCancelModal}
        onConfirm={handleCancelSubscription}
        isProcessing={isProcessing}
      />
    </Flex>
  );
});

BillingPage.displayName = 'BillingPage';

const getCancellationMessage = (subscription: SubscriptionStatus) => {
  const endDate = getEffectiveEndDate(subscription);
  return endDate ? (
    <>
      You can use it until <Text as="span">{formatEndDate(endDate)}</Text>. You can reactivate it to
      continue service.
    </>
  ) : (
    <>You can reactivate it to continue service.</>
  );
};

export { BillingPage };
