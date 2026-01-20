import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { authorizeIntercom } from '../../utils/intercomOAuth';
import type { Integration } from '../../types';
import { connectorConfigQueryKey } from '../../api/config';
import { useIntercomStatus, useIntercomDisconnect } from '../../connectors/intercom/api';
import { useSourceStats } from '../../hooks/useSourceStats';
import { getSupportContactText } from '../../constants';

interface IntercomIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const IntercomIntegration: FC<IntercomIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { data: intercomStatus } = useIntercomStatus();
  const disconnectMutation = useIntercomDisconnect();
  const isConnected = intercomStatus?.connected ?? false;
  const { data: sourceStats } = useSourceStats({ enabled: isConnected });

  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [showDisconnectSuccess, setShowDisconnectSuccess] = useState(false);

  const intercomStats = sourceStats?.intercom;
  const indexedDocuments = intercomStats?.indexed ?? 0;
  const formatNumber = (value: number): string => value.toLocaleString();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      navigate('/integrations/intercom', { replace: true });

      setHasError(false);
      setIsConnecting(false);
    }

    if (error) {
      setHasError(true);
      navigate('/integrations/intercom', { replace: true });

      setIsConnecting(false);
    }
  }, [location.search, navigate, onInlineComplete, queryClient]);

  const handleConnect = () => {
    setHasError(false);
    setIsConnecting(true);
    authorizeIntercom();
  };

  const handleDisconnect = async () => {
    try {
      await disconnectMutation.mutateAsync();
      setHasError(false);
      setShowDisconnectSuccess(true);
      // Hide success message after 3 seconds
      setTimeout(() => setShowDisconnectSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to disconnect Intercom:', error);
      setHasError(true);
      setShowDisconnectSuccess(false);
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
      title: 'Connect Intercom',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your Intercom account to sync conversations, contacts, and help center content
            with Grapevine.
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
                  ✓ Intercom Account Connected
                </Text>
                <Text fontSize="sm" color="secondary">
                  Your Intercom account is successfully connected and indexing data.
                </Text>
                <Flex direction="column" gap={4}>
                  <Text fontSize="sm" color="secondary">
                    Indexed documents: {formatNumber(indexedDocuments)}
                  </Text>
                </Flex>
              </Flex>

              <Flex direction="row" gap={8}>
                <Button onClick={handleConnect} kind="secondary" size="sm">
                  Reconnect Intercom
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
                    ✓ Intercom Disconnected Successfully
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    Your Intercom account has been disconnected and access tokens have been removed.
                  </Text>
                </Flex>
              )}

              <Text>
                Click the button below to connect your Intercom account. You'll be redirected to
                Intercom to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to Intercom...' : 'Connect Intercom Account'}
              </Button>

              {hasError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    {disconnectMutation.isError
                      ? 'Could not disconnect from Intercom'
                      : 'Could not connect to Intercom'}
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
