import { useState, useEffect, useMemo } from 'react';
import type { FC, ReactNode } from 'react';
import { BaseIntegration } from './BaseIntegration';
import { useWebhookUrls } from '../../hooks/useWebhookUrls';
import { integrationSteps } from '../../data/integrationSteps';
import { apiClient } from '../../api/client';
import type { Integration, ConnectionStep } from '../../types';
import { connectorConfigQueryKey, useAllConfig, useSetConfigValue } from '../../api/config';
import { useQueryClient } from '@tanstack/react-query';

interface NotionIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const NotionIntegration: FC<NotionIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();

  // Poll for webhook secret when listening
  const [isListening, setIsListening] = useState(false);
  const { data: configData } = useAllConfig({
    refetchInterval: isListening ? 5000 : undefined,
  });
  const { mutateAsync: updateConfigValue, isPending: isUpdatingConfig } = useSetConfigValue();

  const webhookUrls = useWebhookUrls();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepInputs, setStepInputs] = useState<Record<number, string>>({});
  const [isCompleting, setIsCompleting] = useState(false);
  const [hasSecretBeenCopied, setHasSecretBeenCopied] = useState(false);
  const [linkClickStates, setLinkClickStates] = useState<Record<string, boolean>>({});
  const [setupNonce, setSetupNonce] = useState<string | null>(null);
  const [nonceError, setNonceError] = useState<string | null>(null);

  const steps = useMemo(() => integrationSteps.notion || [], []);

  // Initialize step inputs with existing config values
  useEffect(() => {
    const initialInputs: Record<number, string> = {};

    // Step 1 is "Copy Integration Token" - pre-fill with existing NOTION_TOKEN
    if (configData?.NOTION_TOKEN) {
      initialInputs[1] = configData.NOTION_TOKEN;
    }

    setStepInputs(initialInputs);
  }, [configData?.NOTION_TOKEN]);

  // Stop listening when webhook secret is received and reset copy state
  useEffect(() => {
    if (configData?.NOTION_WEBHOOK_SECRET && isListening) {
      setIsListening(false);
    }
    // Reset hasSecretBeenCopied when secret changes
    setHasSecretBeenCopied(false);
  }, [configData?.NOTION_WEBHOOK_SECRET, isListening]);

  // Set initial step to last step when modal opens and webhook secret exists (completed)
  useEffect(() => {
    if (isModalOpen && steps.length > 0 && configData?.NOTION_WEBHOOK_SECRET) {
      setCurrentStepIndex(steps.length - 1);
    }
  }, [isModalOpen, steps.length, configData?.NOTION_WEBHOOK_SECRET]);

  // Initialize nonce when reaching the webhook configuration step
  useEffect(() => {
    const currentStep = steps[currentStepIndex];
    if (currentStep?.title === 'Configure Webhook' && !setupNonce) {
      initializeSetupNonce();
    }
  }, [currentStepIndex, steps, setupNonce]);

  // Auto-start listening when reaching the webhook verification step
  useEffect(() => {
    const currentStep = steps[currentStepIndex];
    if (currentStep?.title === 'Verify Webhook' && !configData?.NOTION_WEBHOOK_SECRET) {
      setIsListening(true);
    }
  }, [currentStepIndex, configData?.NOTION_WEBHOOK_SECRET, steps]);

  const initializeSetupNonce = async () => {
    try {
      setNonceError(null);
      const response = await apiClient.post<{ nonce: string }>('/api/notion/init-setup');
      setSetupNonce(response.nonce);
    } catch (error) {
      console.error('Failed to initialize Notion setup nonce:', error);
      setNonceError('Failed to generate secure setup link. Please try again.');
    }
  };

  const webhookUrlWithNonce = useMemo(() => {
    if (!webhookUrls?.NOTION || !setupNonce) return webhookUrls?.NOTION;
    return `${webhookUrls.NOTION}?setup_nonce=${setupNonce}`;
  }, [webhookUrls?.NOTION, setupNonce]);

  const handleLinkClick = (linkKey: string) => {
    setLinkClickStates((prev) => ({
      ...prev,
      [linkKey]: true,
    }));
  };

  const isStepValid = (stepIndex: number): boolean => {
    const currentStep = steps[stepIndex];

    if (!currentStep?.requiresInput || !currentStep?.validateInput) {
      return true;
    }

    // Special handling for webhook verification step
    if (currentStep.title === 'Verify Webhook') {
      return !!configData?.NOTION_WEBHOOK_SECRET && hasSecretBeenCopied;
    }

    const inputValue = stepInputs[stepIndex] || '';
    return currentStep.validateInput(inputValue, inputValue, false, linkClickStates);
  };

  const handleComplete = async () => {
    // Trigger Notion backfill and mark Notion setup complete if we're on the last step
    if (currentStepIndex === steps.length - 1) {
      setIsCompleting(true);
      try {
        const response = await apiClient.post('/api/notion/start-ingest');
        console.log('Notion backfill started:', response);
        // api/notion/start-ingest sets NOTION_COMPLETE to true in the backend
        queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      } catch (error) {
        console.error('Failed to start Notion backfill:', error);
        // We still allow completion even if backfill fails to start
        // since the integration is already configured
      } finally {
        setIsCompleting(false);
      }
    }

    if (renderInline && onInlineComplete) {
      onInlineComplete();
    } else {
      // Close the modal
      onModalOpenChange(false);
    }
  };

  const handleStepChange = async (newStepIndex: number) => {
    // Save configuration when moving forward from input steps
    if (newStepIndex > currentStepIndex) {
      // Notion token is on step 1
      if (currentStepIndex === 1) {
        const notionToken = stepInputs[1];
        if (notionToken && notionToken.trim()) {
          await updateConfigValue({
            key: 'NOTION_TOKEN',
            value: notionToken.trim(),
          });
        }
      }
    }
    setCurrentStepIndex(newStepIndex);
  };

  const handleCopyWebhookUrl = () => {
    const url = webhookUrls?.NOTION;
    if (url) {
      navigator.clipboard.writeText(url);
    }
  };

  const handleCopySecret = () => {
    const secret = configData?.NOTION_WEBHOOK_SECRET;
    if (secret) {
      navigator.clipboard.writeText(secret);
      setHasSecretBeenCopied(true);
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
        webhookUrls: {
          ...webhookUrls,
          NOTION: webhookUrlWithNonce, // Use webhook URL with nonce
        },
        onCopyWebhookUrl: handleCopyWebhookUrl,
        onListenForToken: () => setIsListening(true),
        isListening,
        webhookSecret: configData?.NOTION_WEBHOOK_SECRET,
        onCopySecret: handleCopySecret,
        linkClickStates,
        onLinkClick: handleLinkClick,
        nonceError,
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
      isCompleting={isCompleting || isUpdatingConfig}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
    />
  );
};
