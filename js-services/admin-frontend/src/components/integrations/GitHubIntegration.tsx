import { useState, useEffect, useRef } from 'react';
import type { FC, ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useQueryClient } from '@tanstack/react-query';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import type { Integration, ConnectionStep } from '../../types';
import { IS_LOCAL, IS_STAGING } from '../../constants';
import { useTrackEvent } from '../../hooks/useTrackEvent';
import {
  fetchGithubStatus,
  githubStatusQueryKey,
  useGithubStatus,
} from '../../connectors/github/api';
import { connectorConfigQueryKey } from '../../api/config';

const AUTH_TYPE_PAT = 'pat';
const DEPRECATION_WARNING_BG_COLOR = '#fff3cd';
const DEPRECATION_WARNING_BORDER_COLOR = '#ffc107';
const DEPRECATION_WARNING_TEXT_COLOR = '#856404';

interface GitHubIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

const GITHUB_APP_NAME = IS_LOCAL
  ? 'grapevine-integration-dev'
  : IS_STAGING
    ? 'grapevine-integration-staging'
    : 'grapevine-integration';

export const GitHubIntegration: FC<GitHubIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();

  const [isPolling, setIsPolling] = useState(false);
  const { data: githubStatus } = useGithubStatus({
    refetchInterval: isModalOpen && isPolling ? 2000 : undefined,
  });

  const { trackEvent } = useTrackEvent();
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  const [popupWindow, setPopupWindow] = useState<Window | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const setupStartTimeRef = useRef<number | null>(null);

  const installationUrl = `https://github.com/apps/${GITHUB_APP_NAME}/installations/new`;

  const handleManagePermissionsClick = async () => {
    if (!githubStatus?.installation_id) {
      // Fallback to general installations page
      window.open('https://github.com/settings/installations', '_blank', 'noopener,noreferrer');
      return;
    }

    try {
      const response = await apiClient.get<{ url: string; type: string; accountName: string }>(
        `/api/github/installation/${githubStatus.installation_id}/manage-url`
      );
      window.open(response.url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.error('Error getting GitHub installation management URL:', error);
      // Fallback to general installations page
      window.open('https://github.com/settings/installations', '_blank', 'noopener,noreferrer');
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect GitHub?')) {
      return;
    }

    setIsDisconnecting(true);
    try {
      await apiClient.delete('/api/github/disconnect');
      // Invalidate queries to refresh the status
      await queryClient.invalidateQueries({ queryKey: githubStatusQueryKey });
      await queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    } catch (error) {
      console.error('Failed to disconnect GitHub:', error);
      // Error is handled by setting isDisconnecting to false in finally block
    } finally {
      setIsDisconnecting(false);
    }
  };

  // Handle popup window and message events
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Verify origin for security
      if (event.origin !== window.location.origin) {
        return;
      }

      if (event.data.type === 'GITHUB_AUTH_COMPLETE') {
        // Close popup if it's still open
        if (popupWindow && !popupWindow.closed) {
          popupWindow.close();
        }
        setPopupWindow(null);
        setIsPolling(false);

        // Trigger status check and update
        fetchGithubStatus().then((newStatus) => {
          if (newStatus.installed && newStatus.type === 'github_app') {
            queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
            setTimeout(() => {
              onModalOpenChange(false);
            }, 1000);
          }
        });
      }
    };

    window.addEventListener('message', handleMessage);

    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [popupWindow, onModalOpenChange, queryClient]);

  // Monitor popup window for manual closure
  useEffect(() => {
    if (!popupWindow) return;

    const checkClosed = setInterval(() => {
      if (popupWindow.closed) {
        setPopupWindow(null);
        setIsPolling(false);
        clearInterval(checkClosed);
      }
    }, 1000);

    return () => {
      clearInterval(checkClosed);
    };
  }, [popupWindow]);

  // Poll for status changes when modal is open
  useEffect(() => {
    if (isModalOpen && isPolling) {
      if (githubStatus?.installed && githubStatus?.type === 'github_app') {
        setIsPolling(false);
        // Close popup if still open
        if (popupWindow && !popupWindow.closed) {
          popupWindow.close();
        }
        setPopupWindow(null);

        queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });

        // Close modal after successful connection
        setTimeout(() => {
          onModalOpenChange(false);
        }, 1000);
      }
    }
  }, [isModalOpen, isPolling, onModalOpenChange, popupWindow, githubStatus, queryClient]);

  // Initial status check when modal opens and track setup start time
  useEffect(() => {
    if (isModalOpen) {
      queryClient.invalidateQueries({ queryKey: githubStatusQueryKey });

      // Track setup start time when modal opens
      if (!setupStartTimeRef.current) {
        setupStartTimeRef.current = Date.now();
      }
    }
  }, [isModalOpen, queryClient]);

  const isStepValid = (): boolean => {
    return true;
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
      onInlineComplete();
    } else {
      // For GitHub, just close the modal and reset state
      onModalOpenChange(false);
      setCurrentStepIndex(0);
      setIsPolling(false);
      setupStartTimeRef.current = null;
    }
  };

  const handleInstallClick = () => {
    // Store current URL for return navigation
    const returnUrl = window.location.pathname + window.location.search;
    localStorage.setItem('github_return_url', returnUrl);

    // Start polling when user clicks install
    setIsPolling(true);

    // Calculate popup position (centered on screen)
    const width = 900;
    const height = 600;
    const left = Math.round((window.screen.width - width) / 2);
    const top = Math.round((window.screen.height - height) / 2);

    // Open GitHub App installation in popup
    const popup = window.open(
      installationUrl,
      'github-installation',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );

    setPopupWindow(popup);
  };

  const handleStepChange = async (newStepIndex: number) => {
    setCurrentStepIndex(newStepIndex);
  };

  // Single step for GitHub OAuth flow
  const steps: ConnectionStep[] = [
    {
      title:
        githubStatus?.installed && githubStatus?.type === 'github_app'
          ? 'Manage GitHub Integration'
          : 'Install GitHub App',
      content: () => (
        <Flex direction="column" gap={16}>
          {githubStatus?.installed && githubStatus?.type === 'github_app' ? (
            // Already installed - show management options
            <>
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
                    <strong>✓ GitHub Connected Successfully</strong>
                  </Text>
                </div>
              </Flex>

              <Text fontSize="md">
                Need to change which repositories Grapevine can access or update permissions?
              </Text>

              <button
                onClick={handleManagePermissionsClick}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  padding: '12px 24px',
                  backgroundColor: '#24292e',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  textDecoration: 'none',
                }}
              >
                <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
                Manage GitHub Permissions
              </button>
            </>
          ) : githubStatus?.installed && githubStatus?.type === AUTH_TYPE_PAT ? (
            <>
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: DEPRECATION_WARNING_BG_COLOR,
                  borderRadius: '8px',
                  border: `1px solid ${DEPRECATION_WARNING_BORDER_COLOR}`,
                  color: DEPRECATION_WARNING_TEXT_COLOR,
                }}
              >
                <Text fontSize="sm" fontWeight="semibold">
                  ⚠️ Migration Required: Legacy Personal Access Token Authentication
                </Text>
                <Text fontSize="sm">
                  You're currently using the legacy Personal Access Token (PAT) authentication
                  method. Please migrate to the GitHub App for improved security, better webhook
                  reliability, and easier permission management.
                </Text>
                <Text fontSize="sm">
                  To migrate: Click "Disconnect" below. After disconnecting, you'll be able to
                  install the GitHub App for improved security and reliability.
                </Text>
              </Flex>

              <Text fontSize="md">
                Install the Grapevine GitHub App to automatically sync your repositories, pull
                requests, issues, and code changes with zero configuration.
              </Text>

              <Button
                onClick={handleDisconnect}
                kind="danger"
                size="md"
                loading={isDisconnecting}
                disabled={isDisconnecting}
              >
                Disconnect
              </Button>

              {isPolling && (
                <Flex
                  direction="column"
                  gap={8}
                  style={{
                    padding: '12px',
                    backgroundColor: DEPRECATION_WARNING_BG_COLOR,
                    borderRadius: '8px',
                    border: `1px solid ${DEPRECATION_WARNING_BORDER_COLOR}`,
                  }}
                >
                  <div style={{ color: DEPRECATION_WARNING_TEXT_COLOR }}>
                    <Text fontSize="sm">
                      <strong>Waiting for installation...</strong>
                    </Text>
                    <Text fontSize="sm">
                      Complete the GitHub App installation in the new tab. This window will
                      automatically update when finished.
                    </Text>
                  </div>
                </Flex>
              )}
            </>
          ) : (
            // Not installed - show installation instructions
            <>
              <Text fontSize="md">
                Install the Grapevine GitHub App to automatically sync your repositories, pull
                requests, issues, and code changes with zero configuration.
              </Text>

              <Flex direction="column" gap={12}>
                <Text fontSize="md" fontWeight="semibold">
                  Installation is simple:
                </Text>
                <Flex direction="column" gap={4} pl={16}>
                  <Text fontSize="md">1. Click the "Install GitHub App" button below</Text>
                  <Text fontSize="md">2. Choose which repositories to grant access to</Text>
                  <Text fontSize="md">
                    3. Complete the installation - you'll be automatically redirected back
                  </Text>
                </Flex>
              </Flex>

              <button
                onClick={handleInstallClick}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  padding: '12px 24px',
                  backgroundColor: '#24292e',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  textDecoration: 'none',
                }}
              >
                <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
                {isPolling ? 'Waiting for installation...' : 'Install GitHub App'}
              </button>

              {isPolling && (
                <Flex
                  direction="column"
                  gap={8}
                  style={{
                    padding: '12px',
                    backgroundColor: '#fff3cd',
                    borderRadius: '8px',
                    border: '1px solid #ffeaa7',
                  }}
                >
                  <div style={{ color: '#856404' }}>
                    <Text fontSize="sm">
                      <strong>Waiting for installation...</strong>
                    </Text>
                    <Text fontSize="sm">
                      Complete the GitHub App installation in the new tab. This window will
                      automatically update when finished.
                    </Text>
                  </div>
                </Flex>
              )}
            </>
          )}
        </Flex>
      ),
    },
  ];

  const renderStepContent = (step: ConnectionStep, _stepIndex: number): ReactNode => {
    if (!step) {
      return null;
    }

    // If the content is a function (for interactive steps), call it with props
    if (typeof step.content === 'function') {
      return step.content({
        inputValue: '',
        onInputChange: () => {},
        hasError: false,
      });
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
      isCompleting={false}
      renderStepContent={renderStepContent}
      hideNavigation={true}
      renderInline={renderInline}
    />
  );
};
