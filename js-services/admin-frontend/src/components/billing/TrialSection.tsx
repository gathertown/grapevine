import type { FC } from 'react';
import { useState } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import type { TrialStatus, SubscriptionStatus } from '../../types';
import { SectionContainer } from '../shared/SectionContainer';
import { SectionHeader } from '../shared/SectionHeader';
import { PlanPickerModal } from './PlanPickerModal';

interface TrialSectionProps {
  trial: TrialStatus;
  subscription: SubscriptionStatus;
  showInline?: boolean;
}

export const TrialSection: FC<TrialSectionProps> = ({
  trial,
  subscription,
  showInline = false,
}) => {
  const [showPlanPicker, setShowPlanPicker] = useState(false);

  const content = (
    <Flex direction="row" align="center" justify="space-between">
      <Flex direction="column" gap={4}>
        <Flex direction="column" gap={4}>
          <Text fontSize="md" fontWeight="semibold">
            Your first month of using Grapevine is on us 🙂
          </Text>
          <Text fontSize="md" color="tertiary">
            {trial.daysRemaining > 0 ? (
              <>
                Choose a plan to continue using Grapevine after{' '}
                <Text as="span" fontWeight="semibold">
                  {new Date(trial.trialEndDate).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </Text>
              </>
            ) : (
              'Choose a plan to continue using Grapevine'
            )}
          </Text>
        </Flex>
      </Flex>
      {!subscription.hasActiveSubscription && (
        <Button
          kind={trial.daysRemaining > 0 ? 'secondary' : 'primary'}
          onClick={() => setShowPlanPicker(true)}
        >
          Choose a plan
        </Button>
      )}
    </Flex>
  );

  return (
    <>
      {showInline ? (
        <Flex direction="column" justify="space-between" gap={16} p={16}>
          {content}
        </Flex>
      ) : (
        <Flex direction="column">
          <SectionHeader title="Choose a plan" isComplete={false} />
          <SectionContainer isComplete={false}>{content}</SectionContainer>
        </Flex>
      )}

      <PlanPickerModal open={showPlanPicker} onOpenChange={setShowPlanPicker} trialStatus={trial} />
    </>
  );
};
