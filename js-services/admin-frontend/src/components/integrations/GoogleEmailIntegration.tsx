import { useState, useEffect } from 'react';
import type { FC, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import { integrationSteps } from '../../data/integrationSteps';
import type { Integration, ConnectionStep } from '../../types';
import { connectorConfigQueryKey } from '../../api/config';

interface GoogleEmailIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const GoogleEmailIntegration: FC<GoogleEmailIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepInputs, setStepInputs] = useState<Record<number, string>>({});
  const [isCompleting, setIsCompleting] = useState(false);

  // Google Email specific state
  const [googleEmailConfig, setgoogleEmailConfig] = useState<{
    clientId: string | null;
    adminEmail: string | null;
    isConfigured: boolean;
  } | null>(null);
  const [isLoadingGoogleConfig, setIsLoadingGoogleConfig] = useState(false);
  const [hasClientIdCopied, setHasClientIdCopied] = useState(false);
  const [hasScopesCopied, setHasScopesCopied] = useState(false);
  const [linkClickStates, setLinkClickStates] = useState<Record<string, boolean>>({});

  const steps = integrationSteps.google_email || [];

  // Fetch Google Email configuration when modal opens
  useEffect(() => {
    if (isModalOpen && !googleEmailConfig && !isLoadingGoogleConfig) {
      const fetchgoogleEmailConfig = async () => {
        setIsLoadingGoogleConfig(true);
        try {
          const response = await apiClient.get('/api/google-email/configuration');
          setgoogleEmailConfig(
            response as {
              clientId: string | null;
              adminEmail: string | null;
              isConfigured: boolean;
            }
          );
        } catch (error) {
          console.error('Failed to fetch Google Email configuration:', error);
        } finally {
          setIsLoadingGoogleConfig(false);
        }
      };
      fetchgoogleEmailConfig();
    }
  }, [isModalOpen, googleEmailConfig, isLoadingGoogleConfig]);

  const isStepValid = (stepIndex: number): boolean => {
    const currentStep = steps[stepIndex];

    if (!currentStep?.requiresInput || !currentStep?.validateInput) {
      return true;
    }

    // Special handling for Google Email steps
    const inputValue = stepInputs[stepIndex] || '';
    return currentStep.validateInput(
      inputValue,
      '',
      false,
      linkClickStates,
      googleEmailConfig?.clientId || null,
      hasScopesCopied
    );
  };

  const handleComplete = async () => {
    setIsCompleting(true);
    try {
      const adminEmail = stepInputs[currentStepIndex] || '';
      if (!adminEmail.trim()) {
        console.error('Admin email is required');
        return;
      }

      // Save the configuration
      await apiClient.post('/api/google-email/configuration', {
        adminEmail: adminEmail.trim(),
      });

      // Refresh config context to reflect the change
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });

      if (renderInline && onInlineComplete) {
        onInlineComplete();
      } else {
        // Close the modal and reset state
        onModalOpenChange(false);
        setCurrentStepIndex(0);
        setStepInputs({});
        setHasClientIdCopied(false);
        setHasScopesCopied(false);
        setLinkClickStates({});
      }
    } catch (error) {
      console.error('Failed to complete Google Email integration:', error);
    } finally {
      setIsCompleting(false);
    }
  };

  const handleCopyClientId = () => {
    if (googleEmailConfig?.clientId) {
      navigator.clipboard.writeText(googleEmailConfig.clientId);
      setHasClientIdCopied(true);
    }
  };

  const handleCopyScopesUrl = () => {
    const scopes =
      'https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/gmail.readonly';
    navigator.clipboard.writeText(scopes);
    setHasScopesCopied(true);
  };

  const handleLinkClick = (linkKey: string) => {
    setLinkClickStates((prev) => ({
      ...prev,
      [linkKey]: true,
    }));
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
        linkClickStates,
        onLinkClick: handleLinkClick,
        // Google Email specific props
        clientId: isLoadingGoogleConfig ? undefined : googleEmailConfig?.clientId || undefined,
        onCopyClientId: handleCopyClientId,
        hasClientIdCopied,
        onCopyScopesUrl: handleCopyScopesUrl,
        hasScopesCopied,
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
      isCompleting={isCompleting}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
    />
  );
};
