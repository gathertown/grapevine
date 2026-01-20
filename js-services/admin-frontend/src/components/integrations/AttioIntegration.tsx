import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import type { Integration } from '../../types';
import { connectorConfigQueryKey, connectorStatusesQueryKey, useAllConfig } from '../../api/config';
import { SUPPORT_EMAIL } from '../../constants';

const ATTIO_API_INSTALL = '/api/attio/install';
const ATTIO_API_DISCONNECT = '/api/attio/disconnect';
const ATTIO_INTEGRATION_PATH = '/integrations/attio';
const ATTIO_ACCESS_TOKEN_CONFIG_KEY = 'ATTIO_ACCESS_TOKEN';

interface AttioIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

const useDisconnectAttio = (onDisconnectSuccess?: () => void) => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete(ATTIO_API_DISCONNECT),
    onSuccess: () => {
      // Invalidate config query so it refetches
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      // Invalidate connector statuses to update onboarding progress
      queryClient.invalidateQueries({ queryKey: connectorStatusesQueryKey });
      // Call the success callback to reset local state
      onDisconnectSuccess?.();
    },
  });

  return { mutate, isPending, error };
};

export const AttioIntegration: FC<AttioIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { data: configData } = useAllConfig();
  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Reset local state when disconnect succeeds
  const handleDisconnectSuccess = () => {
    setIsConnecting(false);
    setHasError(false);
  };

  const {
    mutate: disconnectAttio,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectAttio(handleDisconnectSuccess);

  // Check if Attio is already connected (has access token)
  const isConnected = !!configData?.[ATTIO_ACCESS_TOKEN_CONFIG_KEY];

  // Check for success or error parameters in URL
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      // Refresh config to get updated status
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      // Clear the URL parameter
      navigate(ATTIO_INTEGRATION_PATH, { replace: true });

      // If we have a complete callback, call it
      if (onInlineComplete) {
        onInlineComplete();
      }

      // Clear any previous errors
      setHasError(false);
      setIsConnecting(false);
    }

    if (error) {
      // Set error state
      setHasError(true);

      // Clear the URL parameter
      navigate(ATTIO_INTEGRATION_PATH, { replace: true });

      // Reset connecting state
      setIsConnecting(false);
    }
  }, [location.search, navigate, onInlineComplete, queryClient]);

  const handleConnect = async () => {
    setHasError(false); // Clear any previous errors
    setIsConnecting(true);
    try {
      // Use apiClient to get the OAuth URL with proper authentication
      const response = await apiClient.get<{ url: string }>(ATTIO_API_INSTALL);

      // Navigate to Attio OAuth URL
      window.location.href = response.url;
    } catch (error) {
      console.error('Error connecting to Attio:', error);
      setIsConnecting(false);
      setHasError(true);
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
      title: 'Connect Attio',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your Attio workspace to sync companies, people, deals, and notes with Grapevine.
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
                  ✓ Attio Connected
                </Text>
                <Text fontSize="sm" color="secondary">
                  Your Attio workspace is successfully connected and indexing data.
                </Text>
              </Flex>

              <Flex direction="column" gap={8}>
                <Text fontSize="sm" color="secondary">
                  To reconnect with a different workspace, disconnect first.
                </Text>
                <Flex gap={8}>
                  <Button
                    onClick={() => disconnectAttio()}
                    loading={isDisconnecting}
                    kind="danger"
                    size="sm"
                  >
                    Disconnect
                  </Button>
                </Flex>
                {disconnectError && (
                  <Text fontSize="sm" color="dangerPrimary">
                    Failed to disconnect. Please try again.
                  </Text>
                )}
              </Flex>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              <Text>
                Click the button below to connect your Attio workspace. You'll be redirected to
                Attio to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to Attio...' : 'Connect Attio Workspace'}
              </Button>

              {hasError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    Could not connect to Attio
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    Please try again or contact Gather support at {SUPPORT_EMAIL}
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
