import { useState, useEffect, useRef } from 'react';
import type { FC, ReactNode } from 'react';
import { BaseIntegration } from './BaseIntegration';
import { useSlackBotConfig } from '../../contexts/SlackBotConfigContext';
import { useUpload } from '../../contexts/UploadContext';
import { integrationSteps } from '../../data/integrationSteps';
import type { Integration, ConnectionStep } from '../../types';
import { useTrackEvent } from '../../hooks/useTrackEvent';
import { useAllConfig } from '../../api/config';

interface SlackIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const SlackIntegration: FC<SlackIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const { isConfigured: slackBotConfigured } = useSlackBotConfig();
  const { data: configData } = useAllConfig();
  const { trackEvent } = useTrackEvent();
  const {
    slackUploadStatus,
    slackExports,
    elapsedTime,
    handleSlackUpload,
    resetSlackUpload,
    fetchSlackExports,
  } = useUpload();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepInputs, setStepInputs] = useState<Record<number, string>>({});
  const setupStartTimeRef = useRef<number | null>(null);

  const steps = integrationSteps.slack || [];

  // Fetch exports on component mount and track setup start time
  useEffect(() => {
    if (isModalOpen) {
      fetchSlackExports();
      // Track setup start time when modal opens
      if (!setupStartTimeRef.current) {
        setupStartTimeRef.current = Date.now();
      }
    }
  }, [isModalOpen, fetchSlackExports]);

  // Reset upload state if previous upload was completed
  useEffect(() => {
    if (slackUploadStatus.completed && !slackUploadStatus.uploading) {
      resetSlackUpload();
    }
  }, [slackUploadStatus.completed, slackUploadStatus.uploading, resetSlackUpload]);

  const isStepValid = (stepIndex: number): boolean => {
    const currentStep = steps[stepIndex];

    // Special handling for Slack upload step
    if (stepIndex === 0) {
      return slackBotConfigured && slackUploadStatus.completed;
    }

    if (!currentStep?.requiresInput || !currentStep?.validateInput) {
      return true;
    }

    const inputValue = stepInputs[stepIndex] || '';
    return currentStep.validateInput(inputValue);
  };

  const handleComplete = async () => {
    // Track integration configuration completion
    const setupDuration = setupStartTimeRef.current
      ? Math.round((Date.now() - setupStartTimeRef.current) / 1000)
      : 0;

    trackEvent('integration_configured', {
      integration_type: integration.id,
      setup_duration_seconds: setupDuration,
      total_steps: steps.length,
    });

    if (renderInline && onInlineComplete) {
      // For inline rendering, call the completion callback
      onInlineComplete();
    } else {
      // For modal rendering, close the modal and reset state
      onModalOpenChange(false);
      setCurrentStepIndex(0);
      setStepInputs({});
      setupStartTimeRef.current = null;
    }
  };

  const renderStepContent = (step: ConnectionStep, stepIndex: number): ReactNode => {
    if (!step) {
      return null;
    }

    // If the content is a function (for interactive steps), call it with props
    if (typeof step.content === 'function') {
      const baseProps = {
        inputValue: stepInputs[stepIndex] || '',
        onInputChange: (value: string) => {
          setStepInputs((prev) => ({
            ...prev,
            [stepIndex]: value,
          }));
        },
        hasError: !isStepValid(stepIndex) && !!stepInputs[stepIndex],
        slackBotConfigured,
        configData,
        // Upload-related props for Slack step
        handleSlackUpload,
        slackUploadStatus,
        resetSlackUpload,
        elapsedTime,
        slackExports,
        onFileChange: (file: File | null) => {
          if (file) {
            handleSlackUpload(file);
          }
        },
      };

      return step.content(baseProps);
    }

    // Otherwise, return the static content
    return step.content;
  };

  return (
    <BaseIntegration
      integration={integration}
      steps={steps}
      isModalOpen={isModalOpen}
      onModalOpenChange={onModalOpenChange}
      currentStepIndex={currentStepIndex}
      onStepChange={setCurrentStepIndex}
      isStepValid={isStepValid}
      onComplete={handleComplete}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
    />
  );
};
