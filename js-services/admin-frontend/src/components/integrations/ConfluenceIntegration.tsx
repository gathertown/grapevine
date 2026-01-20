import { useState, useEffect } from 'react';
import type { FC, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Flex, Text, Input, Button, Loader } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { CopyButton } from '../shared/CopyButton';
import { useAuth } from '../../hooks/useAuth';
import { apiClient } from '../../api/client';
import { getConfig } from '../../lib/config';
import { CONFLUENCE_APP_INSTALLATION_URL } from '../../constants';
import { validateConfluenceSiteUrl } from '../../utils/validation';
import type { Integration, ConnectionStep } from '../../types';
import confluenceSiteUrlImage from '../../assets/setup-screenshots/confluence-site-url.png';
import { confluenceStatusQueryKey, useConfluenceStatus } from '../../connectors/confluence/api';
import { useAllConfig } from '../../api/config';

interface ConfluenceIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const ConfluenceIntegration: FC<ConfluenceIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [isPolling, setIsPolling] = useState(false);
  const { data: confluenceStatus } = useConfluenceStatus({
    refetchInterval: isPolling ? 3000 : undefined,
  });

  const { data: configData } = useAllConfig();
  const config = getConfig();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  const [confluenceSiteUrl, setConfluenceSiteUrl] = useState<string>('');
  const [urlError, setUrlError] = useState<string>('');
  const [hasClickedInstall, setHasClickedInstall] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);

  const [signingSecret, setSigningSecret] = useState<string>('');
  const [isLoadingSigningSecret, setIsLoadingSigningSecret] = useState(false);

  useEffect(() => {
    if (configData?.CONFLUENCE_SITE_URL && !confluenceSiteUrl) {
      setConfluenceSiteUrl(configData.CONFLUENCE_SITE_URL);
    }
  }, [configData?.CONFLUENCE_SITE_URL, confluenceSiteUrl]);

  const isInstallationComplete = confluenceStatus?.installed;

  // Only fetch signing secret when needed for setup (not when already installed)
  useEffect(() => {
    const fetchSigningSecret = async () => {
      if (!user?.tenantId || isInstallationComplete) return;

      setIsLoadingSigningSecret(true);
      try {
        const response = await apiClient.get<{ signingSecret: string }>(
          '/api/confluence/signing-secret'
        );
        setSigningSecret(response.signingSecret);
      } catch (error) {
        console.error('Error fetching Confluence signing secret:', error);
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
      queryClient.invalidateQueries({ queryKey: confluenceStatusQueryKey });
    }
  }, [isModalOpen, queryClient]);

  const handleInstallForgeApp = () => {
    setHasClickedInstall(true);
    window.open(CONFLUENCE_APP_INSTALLATION_URL, '_blank', 'noopener,noreferrer');
  };

  const isStepValid = (stepIndex: number): boolean => {
    if (stepIndex === 0) {
      return !!confluenceSiteUrl && !urlError;
    }
    if (stepIndex === 1) {
      return hasClickedInstall;
    }
    return true;
  };

  const handleSiteUrlChange = (url: string) => {
    setConfluenceSiteUrl(url);

    if (url.trim()) {
      const validation = validateConfluenceSiteUrl(url);
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
    if (currentStepIndex === 0 && newStepIndex === 1 && confluenceSiteUrl.trim()) {
      try {
        await apiClient.post('/api/confluence/save-site', {
          siteUrl: confluenceSiteUrl,
        });
      } catch (error) {
        console.error('Error saving Confluence site URL:', error);
      }
    }

    setCurrentStepIndex(newStepIndex);
  };

  const steps: ConnectionStep[] = isInstallationComplete
    ? [
        {
          title: 'Manage Confluence Integration',
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
                    <strong>✓ Confluence Connected Successfully</strong>
                  </Text>
                </div>
              </Flex>

              <Flex direction="column" gap={12}>
                <Text fontSize="md" fontWeight="semibold">
                  Manage Installation
                </Text>
                <Text fontSize="sm" color="secondary">
                  Access your Confluence app configuration to make changes to your installation:
                </Text>
                <Button
                  onClick={() => {
                    const config = getConfig();
                    const appId = config.CONFLUENCE_APP_ID;
                    const envId = config.CONFLUENCE_APP_ENVIRONMENT_ID;
                    const configUrl = `${confluenceSiteUrl}/wiki/admin/forge?id=ari%3Acloud%3Aecosystem%3A%3Aextension%2F${appId}%2F${envId}%2Fstatic%2Fadmin-configure`;
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
          title: 'Enter Your Confluence Site URL',
          content: () => (
            <Flex direction="column" gap={16}>
              <Flex direction="column" gap={12}>
                <Text fontSize="md" fontWeight="semibold">
                  Follow these steps to find your Confluence site URL:
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
                  <Text fontSize="md">2. Open the Confluence site you want to integrate</Text>
                  <Text fontSize="md">3. Copy the site URL from your browser</Text>
                </Flex>

                <img
                  src={confluenceSiteUrlImage}
                  alt="Screenshot showing Confluence site URL in browser address bar"
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
                  Confluence Site URL
                </Text>
                <Input
                  value={confluenceSiteUrl}
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
          title: 'Install Confluence App',
          content: () => (
            <Flex direction="column" gap={16}>
              <Text fontSize="sm" color="secondary">
                Install the Grapevine app on <strong>{confluenceSiteUrl}</strong> to start indexing
                data:
              </Text>

              <Button onClick={handleInstallForgeApp} kind="primary" size="md">
                <Flex align="center" gap={8}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z" />
                  </svg>
                  Install Confluence App
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
                    href={`${confluenceSiteUrl}/wiki/admin/forge?id=ari%3Acloud%3Aecosystem%3A%3Aextension%2F${config.CONFLUENCE_APP_ID}%2F${config.CONFLUENCE_APP_ENVIRONMENT_ID}%2Fstatic%2Fadmin-configure`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#0052cc', textDecoration: 'underline' }}
                  >
                    Confluence admin configure page
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
