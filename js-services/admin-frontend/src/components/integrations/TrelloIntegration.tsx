import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { authorizeTrello } from '../../utils/trelloOAuth';
import { useIsFeatureEnabled } from '../../api/features';
import type { Integration } from '../../types';
import { useDisconnectTrello, useTrelloStatus } from '../../connectors/trello/api';
import { connectorConfigQueryKey } from '../../api/config';
import { getSupportContactText } from '../../constants';

interface TrelloIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const TrelloIntegration: FC<TrelloIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { data: trelloStatus } = useTrelloStatus();
  const { mutate: disconnectTrello, isPending: isDisconnecting } = useDisconnectTrello();

  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [hasError, setHasError] = useState(false);
  const isConnected = trelloStatus?.configured ?? trelloStatus?.access_token_present;
  const webhookRegistered = trelloStatus?.webhook_registered ?? false;
  const { data: showDisconnect } = useIsFeatureEnabled('internal:features');

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error') === 'true';

    if (success) {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      navigate('/integrations/trello', { replace: true });

      setHasError(false);
      setIsConnecting(false);
    }

    if (error) {
      setHasError(true);
      navigate('/integrations/trello', { replace: true });

      setIsConnecting(false);
    }
  }, [location.search, navigate, onInlineComplete, queryClient]);

  const handleConnect = () => {
    setHasError(false);
    setIsConnecting(true);
    authorizeTrello({
      scope: 'read',
      expiration: 'never',
      name: 'Grapevine',
    });
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
      title: 'Connect Trello',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your Trello account to sync boards, cards, and checklists with Grapevine.
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
                  ✓ Trello Account Connected
                </Text>
                <Text fontSize="sm" color="secondary">
                  Your Trello account is successfully connected and indexing data.
                </Text>
                {webhookRegistered && trelloStatus?.webhook_info?.member_username && (
                  <Text fontSize="xs" color="secondary">
                    Webhook registered for @{trelloStatus.webhook_info.member_username}
                  </Text>
                )}
              </Flex>

              <Flex direction="row" gap={8}>
                <Button onClick={handleConnect} kind="secondary" size="sm">
                  Reconnect Trello
                </Button>
                {showDisconnect && (
                  <Button
                    onClick={() => disconnectTrello()}
                    kind="danger"
                    size="sm"
                    loading={isDisconnecting}
                    disabled={isDisconnecting}
                  >
                    Disconnect (Dev Only)
                  </Button>
                )}
              </Flex>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              <Text>
                Click the button below to connect your Trello account. You'll be redirected to
                Trello to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to Trello...' : 'Connect Trello Account'}
              </Button>

              {hasError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    Could not connect to Trello
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
