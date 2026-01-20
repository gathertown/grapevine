import { useState, useEffect, useMemo } from 'react';
import type { FC, ReactNode } from 'react';
import { BaseIntegration } from './BaseIntegration';
import { integrationSteps } from '../../data/integrationSteps';
import { startSalesforceOAuth } from '../../utils/salesforceOAuth';
import type { Integration, ConnectionStep } from '../../types';
import { ConfigData, useAllConfig } from '../../api/config';

interface SalesforceIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

/**
 * Check if Salesforce is fully configured with valid tokens and org info
 */
const isSalesforceConfigured = (configData: ConfigData): boolean => {
  const refreshToken = configData.SALESFORCE_REFRESH_TOKEN || '';
  const instanceUrl = configData.SALESFORCE_INSTANCE_URL || '';
  const orgId = configData.SALESFORCE_ORG_ID || '';

  return refreshToken.trim().length > 0 && instanceUrl.trim().length > 0 && orgId.trim().length > 0;
};

export const SalesforceIntegration: FC<SalesforceIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const { data: configData } = useAllConfig();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepInputs, setStepInputs] = useState<Record<number, string>>({});
  const [linkClickStates, setLinkClickStates] = useState<Record<string, boolean>>({});

  const steps = useMemo(() => integrationSteps.salesforce || [], []);

  // Salesforce connector is done if all required fields exist. See also: validation.ts
  const isConnected = !!configData && isSalesforceConfigured(configData);

  // Set initial step to last step when modal opens and Salesforce is connected
  // Also advance to last step when connection is established (e.g., after OAuth callback)
  useEffect(() => {
    if (steps.length > 0 && isConnected) {
      setCurrentStepIndex(steps.length - 1);
    }
  }, [steps.length, isConnected]);

  const handleLinkClick = async (linkKey: string) => {
    setLinkClickStates((prev) => ({
      ...prev,
      [linkKey]: true,
    }));

    // Handle OAuth flow initiation using oidc-client-ts
    if (linkKey === 'authenticateSalesforce') {
      try {
        await startSalesforceOAuth();
      } catch (error) {
        console.error('Error starting Salesforce OAuth:', error);
      }
    }
  };

  const isStepValid = (stepIndex: number): boolean => {
    const currentStep = steps[stepIndex];

    if (!currentStep?.requiresInput || !currentStep?.validateInput) {
      return true;
    }

    const inputValue = stepInputs[stepIndex] || '';
    return currentStep.validateInput(inputValue, inputValue, false, linkClickStates);
  };

  const handleComplete = async () => {
    if (renderInline && onInlineComplete) {
      onInlineComplete();
    } else {
      onModalOpenChange(false);
    }
  };

  const handleStepChange = async (newStepIndex: number) => {
    setCurrentStepIndex(newStepIndex);
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
        isConnected,
        configData,
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
      onStepChange={handleStepChange}
      isStepValid={isStepValid}
      onComplete={handleComplete}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
      hideNavigation={false}
      isConnected={isConnected}
    />
  );
};
