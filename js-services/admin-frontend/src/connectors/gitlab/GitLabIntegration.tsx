import { useState, useEffect, useCallback } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from '../../components/integrations/BaseIntegration';
import { authorizeGitLab } from './gitlabOAuth';
import type { Integration } from '../../types';
import { connectorConfigQueryKey } from '../../api/config';
import { useGitLabStatus, useGitLabDisconnect } from './api';
import { useSourceStats } from '../../hooks/useSourceStats';
import { getSupportContactText } from '../../constants';

interface GitLabIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const GitLabIntegration: FC<GitLabIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { data: gitlabStatus } = useGitLabStatus();
  const disconnectMutation = useGitLabDisconnect();
  const isConnected = gitlabStatus?.connected ?? false;
  const { data: sourceStats } = useSourceStats({ enabled: isConnected });

  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [showDisconnectSuccess, setShowDisconnectSuccess] = useState(false);

  const gitlabStats = sourceStats?.gitlab;
  const indexedDocuments = gitlabStats?.indexed ?? 0;
  const formatNumber = useCallback((value: number): string => value.toLocaleString(), []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      navigate('/integrations/gitlab', { replace: true });
      setHasError(false);
      setIsConnecting(false);
    }

    if (error) {
      setHasError(true);
      navigate('/integrations/gitlab', { replace: true });
      setIsConnecting(false);
    }
  }, [location.search, navigate, queryClient]);

  const handleConnect = useCallback(() => {
    setHasError(false);
    setIsConnecting(true);
    authorizeGitLab();
  }, []);

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectMutation.mutateAsync();
      setHasError(false);
      setShowDisconnectSuccess(true);
      setTimeout(() => setShowDisconnectSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to disconnect GitLab:', error);
      setHasError(true);
      setShowDisconnectSuccess(false);
    }
  }, [disconnectMutation]);

  const handleComplete = useCallback(() => {
    if (renderInline && onInlineComplete) {
      onInlineComplete();
    } else {
      onModalOpenChange(false);
    }
  }, [renderInline, onInlineComplete, onModalOpenChange]);

  const steps = [
    {
      title: 'Connect GitLab',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your GitLab account to sync merge requests, issues, and repository content with
            Grapevine.
          </Text>

          {isConnected ? (
            <Flex direction="column" gap={12}>
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
                <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
                  GitLab Account Connected
                </Text>
                <Text fontSize="sm" color="secondary">
                  Your GitLab account is successfully connected and indexing data.
                </Text>
                {gitlabStatus?.username && (
                  <Text fontSize="sm" color="secondary">
                    Connected as: {gitlabStatus.name || gitlabStatus.username}
                  </Text>
                )}
                <Flex direction="column" gap={4}>
                  <Text fontSize="sm" color="secondary">
                    Indexed documents: {formatNumber(indexedDocuments)}
                  </Text>
                </Flex>
              </Flex>

              <Flex direction="row" gap={8}>
                <Button onClick={handleConnect} kind="secondary" size="sm">
                  Reconnect GitLab
                </Button>
                <Button
                  onClick={handleDisconnect}
                  kind="danger"
                  size="sm"
                  loading={disconnectMutation.isPending}
                  disabled={disconnectMutation.isPending}
                >
                  {disconnectMutation.isPending ? 'Disconnecting...' : 'Disconnect'}
                </Button>
              </Flex>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              {showDisconnectSuccess && (
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
                  <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
                    GitLab Disconnected Successfully
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    Your GitLab account has been disconnected and access tokens have been removed.
                  </Text>
                </Flex>
              )}

              <Text>
                Click the button below to connect your GitLab account. You'll be redirected to
                GitLab to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to GitLab...' : 'Connect GitLab Account'}
              </Button>

              {hasError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    {disconnectMutation.isError
                      ? 'Could not disconnect from GitLab'
                      : 'Could not connect to GitLab'}
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    {getSupportContactText()}
                  </Text>
                </Flex>
              )}
            </Flex>
          )}
        </Flex>
      ),
    },
  ];

  return (
    <BaseIntegration
      integration={integration}
      steps={steps}
      isModalOpen={isModalOpen}
      onModalOpenChange={onModalOpenChange}
      currentStepIndex={0}
      onStepChange={() => {}}
      isStepValid={() => true}
      onComplete={async () => handleComplete()}
      renderStepContent={(step) => (typeof step.content === 'function' ? null : step.content)}
      renderInline={renderInline}
    />
  );
};
