import type { FC, ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { Flex } from '@gathertown/gather-design-system';
import { StepProgressBar, StepNavigation, SetupHeader } from '../shared';
import { IntegrationModal } from './IntegrationModal';
import type { Integration, ConnectionStep } from '../../types';
import { newrelic } from '@corporate-context/frontend-common';
import { useTrackEvent } from '../../hooks/useTrackEvent';

interface BaseIntegrationProps {
  integration: Integration;
  steps: ConnectionStep[];
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  currentStepIndex: number;
  onStepChange: (index: number) => void;
  isStepValid: (stepIndex: number) => boolean;
  onComplete: () => Promise<void>;
  isCompleting?: boolean;
  renderStepContent: (step: ConnectionStep, stepIndex: number) => ReactNode;
  hideNavigation?: boolean;
  renderInline?: boolean;
  hideComplete?: boolean;
  isConnected?: boolean;
  pendingVerification?: boolean;
  completionButtonText?: string;
}

export const BaseIntegration: FC<BaseIntegrationProps> = ({
  integration,
  steps,
  isModalOpen,
  onModalOpenChange,
  currentStepIndex,
  onStepChange,
  isStepValid,
  onComplete,
  isCompleting = false,
  renderStepContent,
  hideNavigation = false,
  renderInline = false,
  hideComplete = false,
  isConnected = false,
  pendingVerification = false,
  completionButtonText = 'Complete',
}) => {
  const { trackEvent } = useTrackEvent();
  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === steps.length - 1;
  const hasLoggedPendingRef = useRef<boolean>(false);

  useEffect(() => {
    if (pendingVerification) {
      if (!hasLoggedPendingRef.current) {
        hasLoggedPendingRef.current = true;
        newrelic.addPageAction('integrationWaitingForVerification', {
          integrationType: integration.id,
          currentStep: currentStepIndex,
        });
      }
    } else if (hasLoggedPendingRef.current) {
      hasLoggedPendingRef.current = false;
      newrelic.addPageAction('integrationVerificationComplete', {
        integrationType: integration.id,
        currentStep: currentStepIndex,
      });
    }
  }, [pendingVerification, integration.id, currentStepIndex, trackEvent]);
  const currentStep = steps[currentStepIndex];
  const setupStartTimeRef = useRef<number | null>(null);
  const hasTrackedSetupRef = useRef<boolean>(false);

  // Track integration setup start when modal opens
  useEffect(() => {
    if (isModalOpen && !hasTrackedSetupRef.current) {
      setupStartTimeRef.current = Date.now();
      hasTrackedSetupRef.current = true;
      newrelic.addPageAction('integrationSetupStarted', {
        integrationType: integration.id,
        currentStep: currentStepIndex,
      });

      // Track Amplitude event for integration setup start
      trackEvent('integration_setup_started', {
        integration_type: integration.id,
        total_steps: steps.length,
      });
    }
  }, [isModalOpen, integration.id, currentStepIndex, trackEvent, steps.length]);

  const handlePreviousStep = () => {
    if (currentStepIndex > 0) {
      onStepChange(currentStepIndex - 1);
    }
  };

  const handleNextStep = async () => {
    if (!isStepValid(currentStepIndex)) {
      return;
    }

    // Track step completion
    if (currentStep) {
      newrelic.addPageAction('integrationStepCompleted', {
        integrationType: integration.id,
        stepNumber: currentStepIndex + 1,
        stepTitle: currentStep.title || `Step ${currentStepIndex + 1}`,
      });

      // Track Amplitude event for step completion
      trackEvent('integration_step_completed', {
        integration_type: integration.id,
        step_number: currentStepIndex + 1,
        step_title: currentStep.title || `Step ${currentStepIndex + 1}`,
        total_steps: steps.length,
      });
    }

    if (isLastStep) {
      // Track integration completion
      const setupDuration = setupStartTimeRef.current
        ? Math.round((Date.now() - setupStartTimeRef.current) / 1000)
        : 0;
      newrelic.addPageAction('integrationCompleted', {
        integrationType: integration.id,
        setupDurationSeconds: setupDuration,
        totalSteps: steps.length,
      });

      // Track Amplitude event for integration configuration
      trackEvent('integration_configured', {
        integration_type: integration.id,
        setup_duration_seconds: setupDuration,
        total_steps: steps.length,
      });

      await onComplete();
      return;
    }

    if (currentStepIndex < steps.length - 1) {
      onStepChange(currentStepIndex + 1);
    }
  };

  const renderModalContent = () => {
    if (steps.length > 0) {
      const { Icon } = integration;

      return (
        <Flex direction="column" gap={24}>
          {/* Header */}
          <SetupHeader
            title={`Set up ${integration?.name}`}
            primaryIcon={<Icon size={48} />}
            showGrapevine={true}
            showConnection={true}
          />

          {/* Progress Bar - only show if not hiding navigation and more than 1 step */}
          {!hideNavigation && steps.length > 1 && (
            <StepProgressBar
              totalSteps={steps.length}
              currentStep={currentStepIndex + 1}
              completedSteps={currentStepIndex}
            />
          )}

          {/* Current Step Content */}
          <Flex direction="column" gap={16}>
            {currentStep && renderStepContent(currentStep, currentStepIndex)}
          </Flex>
        </Flex>
      );
    }

    return null;
  };

  const getNextButtonText = () => {
    // Custom button text for specific integrations and steps
    if (integration.id === 'salesforce' && currentStepIndex === 0) {
      return "I've setup CDC";
    }
    return undefined; // Use default "Next →"
  };

  const renderFooter = () => {
    if (steps.length > 0 && !hideNavigation && steps.length > 1) {
      const isCurrentStepValid = isStepValid(currentStepIndex);
      const linkTooltip =
        !isCurrentStepValid && currentStep?.requiresLinkClick
          ? 'Please click the link above to continue'
          : undefined;

      // For Salesforce authentication step, hide next button until connected
      const shouldHideNextButton =
        integration.id === 'salesforce' && currentStepIndex === 1 && !isConnected;

      const finalTooltip = pendingVerification
        ? 'Waiting for webhook verification...'
        : linkTooltip;

      return (
        <StepNavigation
          isFirstStep={isFirstStep}
          isLastStep={isLastStep}
          isStepValid={isCurrentStepValid}
          isLoading={isCompleting}
          onPreviousStep={handlePreviousStep}
          onNextStep={handleNextStep}
          nextButtonText={getNextButtonText()}
          completionButtonText={completionButtonText}
          disabledTooltip={finalTooltip}
          hideComplete={hideComplete}
          hideNextButton={shouldHideNextButton || pendingVerification}
        />
      );
    }
    return null;
  };

  if (renderInline) {
    return (
      <Flex direction="column" gap={24} width="100%">
        {renderModalContent()}
        {renderFooter()}
      </Flex>
    );
  }

  return (
    <IntegrationModal open={isModalOpen} onOpenChange={onModalOpenChange} footer={renderFooter()}>
      {renderModalContent()}
    </IntegrationModal>
  );
};
