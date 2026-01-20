import { useState, useEffect } from 'react';
import type { FC, ReactNode } from 'react';
import { Flex, Text, Input, Button, Loader } from '@gathertown/gather-design-system';
import { useQueryClient } from '@tanstack/react-query';
import { BaseIntegration } from './BaseIntegration';
import { CopyButton } from '../shared/CopyButton';
import { useAuth } from '../../hooks/useAuth';
import { apiClient } from '../../api/client';
import { getConfig } from '../../lib/config';
import { JIRA_APP_INSTALLATION_URL } from '../../constants';
import { validateJiraSiteUrl } from '../../utils/validation';
import type { Integration, ConnectionStep } from '../../types';
import jiraStartAtlassian from '../../assets/setup-screenshots/jira-start-atlassian.png';
import { jiraStatusQueryKey, useJiraStatus } from '../../connectors/jira/api';
import { useAllConfig } from '../../api/config';

interface JiraIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const JiraIntegration: FC<JiraIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();

  const { user } = useAuth();
  const { data: configData } = useAllConfig();

  const [isPolling, setIsPolling] = useState(false);
  const { data: jiraStatus } = useJiraStatus({
    refetchInterval: isPolling ? 3000 : undefined,
  });

  const config = getConfig();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [jiraSiteUrl, setJiraSiteUrl] = useState<string>('');
  const [urlError, setUrlError] = useState<string>('');
  const [hasClickedInstall, setHasClickedInstall] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);

  const [signingSecret, setSigningSecret] = useState<string>('');
  const [isLoadingSigningSecret, setIsLoadingSigningSecret] = useState(false);

  useEffect(() => {
    if (configData?.JIRA_SITE_URL && !jiraSiteUrl) {
      setJiraSiteUrl(configData.JIRA_SITE_URL);
    }
  }, [configData?.JIRA_SITE_URL, jiraSiteUrl]);

  const isInstallationComplete = jiraStatus?.installed;

  // Only fetch signing secret when needed for setup (not when already installed)
  useEffect(() => {
    const fetchSigningSecret = async () => {
      if (!user?.tenantId || isInstallationComplete) return;

      setIsLoadingSigningSecret(true);
      try {
        const response = await apiClient.get<{ signingSecret: string }>('/api/jira/signing-secret');
        setSigningSecret(response.signingSecret);
      } catch (error) {
        console.error('Error fetching Jira signing secret:', error);
      } finally {
        setIsLoadingSigningSecret(false);
      }
    };

    fetchSigningSecret();
  }, [user?.tenantId, isInstallationComplete]);

  useEffect(() => {
    if (isInstallationComplete && isPolling) {
      setIsPolling(false);

      if (renderInline && onInlineComplete) {
        onInlineComplete();
      } else {
        onModalOpenChange(false);
        setCurrentStepIndex(0);
        setHasClickedInstall(false);
      }
    }
  }, [isInstallationComplete, isPolling, renderInline, onInlineComplete, onModalOpenChange]);

  useEffect(() => {
    if (isModalOpen) {
      queryClient.invalidateQueries({ queryKey: jiraStatusQueryKey });
    }
  }, [isModalOpen, queryClient]);

  const handleInstallForgeApp = () => {
    setHasClickedInstall(true);
    window.open(JIRA_APP_INSTALLATION_URL, '_blank', 'noopener,noreferrer');
  };

  const isStepValid = (stepIndex: number): boolean => {
    if (stepIndex === 0) {
      return !!jiraSiteUrl && !urlError;
    }
    if (stepIndex === 1) {
      return hasClickedInstall;
    }
    return true;
  };

  const handleSiteUrlChange = (url: string) => {
    setJiraSiteUrl(url);

    if (url.trim()) {
      const validation = validateJiraSiteUrl(url);
      if (!validation.isValid) {
        setUrlError(validation.error || 'Invalid URL');
      } else {
        setUrlError('');
      }
    } else {
      setUrlError('');
    }
  };

  const handleComplete = async () => {
    setIsCompleting(true);
    setIsPolling(true);
    setIsCompleting(false);
  };

  const handleStepChange = async (newStepIndex: number) => {
    if (currentStepIndex === 0 && newStepIndex === 1 && jiraSiteUrl.trim()) {
      try {
        await apiClient.post('/api/jira/save-site', {
          siteUrl: jiraSiteUrl,
        });
      } catch (error) {
        console.error('Error saving Jira site URL:', error);
      }
    }

    setCurrentStepIndex(newStepIndex);
  };

  const steps: ConnectionStep[] = isInstallationComplete
    ? [
        {
          title: 'Manage Jira Integration',
          content: () => (
            <Flex direction="column" gap={16}>
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#d4edda',
                  borderRadius: '8px',
                  border: '1px solid #c3e6cb',
                }}
              >
                <div style={{ color: '#155724' }}>
                  <Text fontSize="sm">
                    <strong>✓ Jira Connected Successfully</strong>
                  </Text>
                </div>
              </Flex>

              <Flex direction="column" gap={12}>
                <Text fontSize="md" fontWeight="semibold">
                  Manage Installation
                </Text>
                <Text fontSize="sm" color="secondary">
                  Access your Jira app configuration to make changes to your installation:
                </Text>
                <Button
                  onClick={() => {
                    const configUrl = `${jiraSiteUrl}/plugins/servlet/upm`;
                    window.open(configUrl, '_blank', 'noopener,noreferrer');
                  }}
                  kind="primary"
                  size="md"
                >
                  <Flex align="center" gap={8}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z" />
                    </svg>
                    Manage Installation
                  </Flex>
                </Button>
              </Flex>
            </Flex>
          ),
        },
      ]
    : [
        {
          title: 'Enter Your Jira Site URL',
          content: () => (
            <Flex direction="column" gap={16}>
              <Flex direction="column" gap={12}>
                <Text fontSize="md" fontWeight="semibold">
                  Follow these steps to find your Jira site URL:
                </Text>
                <Flex direction="column" gap={4} pl={16}>
                  <Text fontSize="md">
                    1. Visit{' '}
                    <a
                      href="https://start.atlassian.com/"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#0052cc', textDecoration: 'underline' }}
                    >
                      https://start.atlassian.com/
                    </a>
                  </Text>
                  <Text fontSize="md">2. Open the Jira site you want to integrate</Text>
                  <Text fontSize="md">3. Copy the site URL from your browser</Text>
                </Flex>

                <img
                  src={jiraStartAtlassian}
                  alt="Screenshot showing start.atlassian.com with Jira sites"
                  style={{
                    width: '100%',
                    maxWidth: '500px',
                    height: 'auto',
                    border: '1px solid #ddd',
                    borderRadius: '8px',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                  }}
                />
              </Flex>

              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="semibold">
                  Jira Site URL
                </Text>
                <Input
                  value={jiraSiteUrl}
                  onChange={(e) => handleSiteUrlChange(e.target.value)}
                  placeholder="https://acme.atlassian.net"
                  hasError={!!urlError}
                />
                {urlError && (
                  <Text fontSize="sm" color="primary">
                    {urlError}
                  </Text>
                )}
              </Flex>
            </Flex>
          ),
        },
        {
          title: 'Install Jira App',
          content: () => (
            <Flex direction="column" gap={16}>
              <Text fontSize="sm" color="secondary">
                Install the Grapevine app on <strong>{jiraSiteUrl}</strong> to start indexing data:
              </Text>

              <Button onClick={handleInstallForgeApp} kind="primary" size="md">
                <Flex align="center" gap={8}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z" />
                  </svg>
                  Install Jira App
                </Flex>
              </Button>
            </Flex>
          ),
        },
        {
          title: 'Set Signing Secret',
          content: () => {
            if (isLoadingSigningSecret) {
              return (
                <Flex direction="column" gap={16}>
                  <Flex align="center" gap={8}>
                    <Loader size="sm" />
                    <Text fontSize="sm" color="secondary">
                      Generating signing secret...
                    </Text>
                  </Flex>
                </Flex>
              );
            }

            return (
              <Flex direction="column" gap={16}>
                <Text fontSize="sm" color="secondary">
                  Copy this signing secret and paste it into the{' '}
                  <a
                    href={`${jiraSiteUrl}/jira/settings/apps/${config.JIRA_APP_ID}/${config.JIRA_APP_ENVIRONMENT_ID}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#0052cc', textDecoration: 'underline' }}
                  >
                    Jira admin configure page
                  </a>{' '}
                  after installing the app:
                </Text>
                <div
                  style={{
                    backgroundColor: '#f5f5f5',
                    padding: '12px',
                    borderRadius: 8,
                    border: '1px solid #e0e0e0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                  }}
                >
                  <code
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '12px',
                      wordBreak: 'break-all',
                    }}
                  >
                    {signingSecret}
                  </code>
                  <CopyButton textToCopy={signingSecret} />
                </div>

                {isPolling && (
                  <Flex
                    direction="column"
                    gap={8}
                    style={{
                      padding: '12px',
                      backgroundColor: '#d1ecf1',
                      borderRadius: '8px',
                      border: '1px solid #bee5eb',
                    }}
                  >
                    <div style={{ color: '#0c5460' }}>
                      <Flex align="center" gap={8}>
                        <Loader size="sm" />
                        <Text fontSize="sm">
                          <strong>Waiting for installation to complete...</strong>
                        </Text>
                      </Flex>
                    </div>
                  </Flex>
                )}
              </Flex>
            );
          },
        },
      ];

  const renderStepContent = (step: ConnectionStep, _stepIndex: number): ReactNode => {
    if (typeof step.content === 'function') {
      // Call the function since our step content functions don't need props
      return (step.content as () => ReactNode)();
    }
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
      isCompleting={isCompleting}
      renderStepContent={renderStepContent}
      hideNavigation={steps.length === 1}
      hideComplete={false}
      renderInline={renderInline}
    />
  );
};
