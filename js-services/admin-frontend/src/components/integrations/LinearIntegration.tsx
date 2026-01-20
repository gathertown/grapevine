import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import type { Integration } from '../../types';
import { connectorConfigQueryKey } from '../../api/config';
import { getSupportContactText } from '../../constants';

interface LinearIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const LinearIntegration: FC<LinearIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [hasLegacyAuth, setHasLegacyAuth] = useState(false);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const response = await apiClient.get<{
          configured: boolean;
          authMethod: 'oauth' | 'api_key' | null;
          hasLegacyAuth: boolean;
        }>('/api/linear/status');
        setIsConnected(response.configured);
        setHasLegacyAuth(response.hasLegacyAuth);
      } catch (error) {
        console.error('Failed to fetch Linear status:', error);
      } finally {
        setIsLoadingStatus(false);
      }
    };

    checkStatus();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      setIsConnected(true);
      setHasLegacyAuth(false); // OAuth connection replaces legacy auth
      setHasError(false);
      setIsConnecting(false);
      navigate('/integrations/linear', { replace: true });
    }

    if (error) {
      setHasError(true);
      setIsConnecting(false);
      navigate('/integrations/linear', { replace: true });
    }
  }, [location.search, navigate, queryClient]);

  const handleConnect = async () => {
    setHasError(false);
    setIsConnecting(true);
    try {
      const response = await apiClient.get<{ url: string }>('/api/linear/install');
      window.location.href = response.url;
    } catch (_error) {
      setIsConnecting(false);
      setHasError(true);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect Linear?')) {
      return;
    }

    setIsDisconnecting(true);
    try {
      await apiClient.delete('/api/linear/disconnect');
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      setIsConnected(false);
      setHasLegacyAuth(false);
    } catch (_error) {
      // Error is handled by setting isDisconnecting to false in finally block
    } finally {
      setIsDisconnecting(false);
    }
  };

  const handleComplete = () => {
    if (renderInline && onInlineComplete) {
      onInlineComplete();
    } else {
      onModalOpenChange(false);
    }
  };

  const steps = [
    {
      title: 'Connect Linear',
      content: (
        <Flex direction="column" gap={16}>
          {isLoadingStatus ? (
            <Text>Loading connection status...</Text>
          ) : (
            <>
              <Text>
                Connect your Linear account to sync issues, projects, and comments with Grapevine.
              </Text>

              {isConnected ? (
                <Flex direction="column" gap={12}>
                  {hasLegacyAuth && (
                    <Flex
                      direction="column"
                      gap={8}
                      style={{
                        padding: '12px',
                        backgroundColor: '#fff3cd',
                        borderRadius: '8px',
                        border: '1px solid #ffc107',
                        color: '#856404',
                      }}
                    >
                      <Text fontSize="sm" fontWeight="semibold">
                        ⚠️ Migration Required: Legacy API Key Authentication
                      </Text>
                      <Text fontSize="sm">
                        You're currently using the legacy API key authentication method. Please
                        migrate to OAuth for improved security and better webhook reliability.
                      </Text>
                      <Text fontSize="sm">
                        To migrate: Click "Disconnect" below, then reconnect using the "Connect
                        Linear Account" button to use OAuth authentication.
                      </Text>
                    </Flex>
                  )}

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
                      ✓ Linear Account Connected
                    </Text>
                    <Text fontSize="sm" color="secondary">
                      Your Linear account is successfully connected and indexing data.
                      {hasLegacyAuth && ' (Using legacy API key authentication)'}
                    </Text>
                  </Flex>

                  <Flex direction="row" gap={8}>
                    <Button onClick={handleConnect} kind="secondary" size="sm">
                      Reconnect Linear
                    </Button>
                    <Button
                      onClick={handleDisconnect}
                      kind="danger"
                      size="sm"
                      loading={isDisconnecting}
                      disabled={isDisconnecting}
                    >
                      Disconnect
                    </Button>
                  </Flex>
                </Flex>
              ) : (
                <Flex direction="column" gap={12}>
                  <Text>
                    Click the button below to connect your Linear account. You'll be redirected to
                    Linear to authorize the connection.
                  </Text>
                  <Button
                    onClick={handleConnect}
                    kind="primary"
                    loading={isConnecting}
                    disabled={isConnecting}
                  >
                    {isConnecting ? 'Redirecting to Linear...' : 'Connect Linear Account'}
                  </Button>

                  {hasError && (
                    <Flex direction="column" gap={8}>
                      <Text color="dangerPrimary" fontWeight="semibold">
                        Could not connect to Linear
                      </Text>
                      <Text fontSize="sm" color="secondary">
                        {getSupportContactText()}
                      </Text>
                    </Flex>
                  )}
                </Flex>
              )}
            </>
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
