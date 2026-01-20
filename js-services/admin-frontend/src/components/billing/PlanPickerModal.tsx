import type { FC } from 'react';
import { useState } from 'react';
import { billingApi } from '../../api/billing';
import { SUPPORT_EMAIL } from '../../constants';
import { tierDefinitions } from '../../utils/tierDefinitions';
import type { TrialStatus } from '../../types';
import {
  Flex,
  Modal,
  Text,
  Button,
  SegmentedControl,
  Icon,
  Box,
  IconButton,
} from '@gathertown/gather-design-system';
import { theme, tokens } from '@gathertown/gather-design-foundations';

interface PlanPickerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPlanSelected?: (plan: string) => void;
  trialStatus?: TrialStatus;
}

// Convert tierDefinitions to the format expected by this component
const plans = Object.entries(tierDefinitions).map(([id, tier]) => ({
  id,
  name: tier.name,
  price: tier.price,
  period: tier.period,
  description: tier.description,
  features: tier.features.map((f) => f.name),
}));

export const PlanPickerModal: FC<PlanPickerModalProps> = ({
  open,
  onOpenChange,
  onPlanSelected,
  trialStatus,
}) => {
  const [selectedPlan, setSelectedPlan] = useState<string>('team');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleSelectPlan = async () => {
    try {
      setIsProcessing(true);

      // Call the onPlanSelected callback if provided (for custom handling)
      onPlanSelected?.(selectedPlan);

      // Create subscription with selected plan
      const response = await billingApi.createSubscription(
        selectedPlan as 'basic' | 'team' | 'pro' | 'ultra'
      );

      if (response && response.url) {
        window.location.href = response.url;
      }
    } catch (err) {
      console.error('Failed to create subscription:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSendAnEmail = async () => {
    if (SUPPORT_EMAIL) {
      window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Enterprise Plan Inquiry')}`;
    }
    onOpenChange(false);
  };

  const selectedPlanDetails = plans.find((plan) => plan.id === selectedPlan);

  const trialEndDate =
    trialStatus &&
    trialStatus.trialEndDate &&
    trialStatus.daysRemaining > 0 &&
    new Date(trialStatus.trialEndDate).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content
        variant="default"
        showOverlay
        style={{
          outline: `1px solid ${theme.border.tertiary}`,
          border: `8px solid ${theme.bg.secondary}`,
          maxWidth: '636px',
          width: '90vw',
          height: 'auto',
        }}
      >
        {/* Close button */}
        <IconButton
          icon="close"
          onClick={() => onOpenChange(false)}
          kind="transparent"
          tabIndex={-1}
          style={{
            position: 'absolute',
            top: tokens.scale[16],
            right: tokens.scale[16],
            zIndex: 1,
          }}
        />

        <Modal.Body style={{ gap: '16px' }}>
          {/* Header */}
          <Flex direction="column" align="flex-start" style={{ textAlign: 'center' }}>
            <Text fontSize="xl" fontWeight="semibold">
              Grapevine is free for the first month 🙂
            </Text>
            {trialEndDate && (
              <Box>
                <Text fontSize="sm" color="tertiary">
                  Choose a plan to continue using Grapevine after{' '}
                </Text>
                <Text fontSize="sm" color="tertiary" fontWeight="bold">
                  {trialEndDate}
                </Text>
              </Box>
            )}
          </Flex>

          {/* Plan Selector */}
          <SegmentedControl
            defaultValue={selectedPlan}
            onSegmentChange={(value) => setSelectedPlan(value)}
            segments={plans.map((plan) => ({
              label: plan.name,
              value: plan.id,
            }))}
          />

          {/* Selected Plan Details */}
          {selectedPlanDetails && (
            <Flex
              direction="column"
              gap={8}
              style={{
                border: `1px solid ${theme.border.secondary}`,
                borderRadius: tokens.scale[12],
                backgroundColor: theme.bg.primary,
              }}
            >
              <Flex
                direction="column"
                gap={8}
                style={{ borderBottom: `1px solid ${theme.border.tertiary}` }}
                p={8}
              >
                <Box px={4}>
                  <Text fontSize="xl" fontWeight="semibold">
                    {selectedPlanDetails.name}
                  </Text>

                  <Flex direction="row" align="baseline">
                    {!trialEndDate || selectedPlan === 'enterprise' ? (
                      <>
                        <Text fontSize="xxl" fontWeight="bold">
                          {selectedPlanDetails.price}
                        </Text>
                        <Box mx={4}>
                          {selectedPlanDetails.period && (
                            <Text fontSize="xs" color="tertiary">
                              {selectedPlanDetails.period}
                            </Text>
                          )}
                        </Box>
                      </>
                    ) : (
                      <>
                        <Text fontSize="xxl" fontWeight="bold">
                          $0
                        </Text>
                        <Box mx={4}>
                          <Text fontSize="xs" color="tertiary">
                            today
                          </Text>
                        </Box>
                        <Text fontSize="xxl" fontWeight="bold">
                          {selectedPlanDetails.price}
                        </Text>
                        <Box mx={4}>
                          {selectedPlanDetails.period && (
                            <Text fontSize="xs" color="tertiary">
                              {selectedPlanDetails.period}
                            </Text>
                          )}
                        </Box>
                        <Text fontSize="xs" color="tertiary">
                          after {trialEndDate}
                        </Text>
                      </>
                    )}
                  </Flex>

                  {selectedPlan !== 'enterprise' && (
                    <Text fontSize="sm">{selectedPlanDetails.description}</Text>
                  )}
                </Box>
              </Flex>

              {/* Enterprise Plan Selection */}
              {selectedPlan === 'enterprise' && (
                <Flex direction="column" gap={12} p={12}>
                  <Text>
                    {SUPPORT_EMAIL
                      ? `Please email us at ${SUPPORT_EMAIL} to discuss enterprise plans`
                      : 'Please contact us to discuss enterprise plans'}
                  </Text>

                  <Button
                    kind="primary"
                    onClick={handleSendAnEmail}
                    style={{
                      alignSelf: 'stretch',
                      justifyContent: 'center',
                      gap: tokens.scale[8],
                      padding: `${tokens.scale[12]} ${tokens.scale[16]}`,
                    }}
                  >
                    <Flex direction="row" align="center" gap={4}>
                      <Icon name="envelope" size="sm" />
                      <Text fontSize="sm" fontWeight="semibold">
                        Send an e-mail
                      </Text>
                    </Flex>
                  </Button>
                </Flex>
              )}

              {selectedPlan !== 'enterprise' && (
                <Flex direction="column" gap={8} p={8}>
                  <Button
                    kind="primary"
                    onClick={handleSelectPlan}
                    disabled={isProcessing}
                    style={{
                      alignSelf: 'stretch',
                      justifyContent: 'center',
                      gap: tokens.scale[8],
                      padding: `${tokens.scale[12]} ${tokens.scale[16]}`,
                    }}
                  >
                    <Flex direction="row" align="center" gap={4}>
                      <Text fontSize="sm" fontWeight="semibold">
                        {isProcessing ? 'Processing...' : 'Select plan'}
                      </Text>
                      {!isProcessing && <Icon name="arrowUpRight" size="sm" />}
                    </Flex>
                  </Button>

                  {/* Features */}
                  <Flex direction="column" gap={12}>
                    {selectedPlanDetails.features.map((feature, index) => (
                      <Flex key={index} direction="row" align="center" gap={4}>
                        <Icon name="check" color="successPrimary" />
                        <Text fontSize="sm">{feature}</Text>
                      </Flex>
                    ))}
                  </Flex>
                </Flex>
              )}
            </Flex>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
};
