import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import type { Integration } from '../../types';
import { connectorConfigQueryKey, useAllConfig } from '../../api/config';
import { getSupportContactText } from '../../constants';

interface HubSpotIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const HubSpotIntegration: FC<HubSpotIntegrationProps> = ({
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

  // Check if HubSpot is already connected
  const isConnected = configData?.HUBSPOT_COMPLETE === 'true';

  // Check for success or error parameters in URL
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      // Refresh config to get updated HUBSPOT_COMPLETE status
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      // Clear the URL parameter
      navigate('/integrations/hubspot', { replace: true });

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
      navigate('/integrations/hubspot', { replace: true });

      // Reset connecting state
      setIsConnecting(false);
    }
  }, [location.search, navigate, onInlineComplete, queryClient]);

  const handleConnect = async () => {
    setHasError(false); // Clear any previous errors
    setIsConnecting(true);
    try {
      // Use apiClient to get the OAuth URL with proper authentication
      const response = await apiClient.get<{ url: string }>('/api/hubspot/install');

      // Navigate to HubSpot OAuth URL
      window.location.href = response.url;
    } catch (error) {
      console.error('Error connecting to HubSpot:', error);
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
      title: 'Connect HubSpot',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your HubSpot account to sync contacts, companies, tickets, and deals with
            Grapevine.
          </Text>

          {isConnected ? (
            <Flex direction="column" gap={12}>
              <Text color="successPrimary">✓ HubSpot is connected</Text>
              <Text fontSize="sm" color="secondary">
                Your HubSpot account is successfully connected and indexing data.
              </Text>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              <Text>
                Click the button below to connect your HubSpot account. You'll be redirected to
                HubSpot to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to HubSpot...' : 'Connect HubSpot Account'}
              </Button>

              {hasError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    Could not connect to HubSpot
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
