import { ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useDisconnectClickup, useOauthClickup } from '../clickupApi';
import { ClickupConfig } from '../clickupConfig';
import { getSupportContactText } from '../../../constants';

const ClickupOauth = ({ config }: { config: ClickupConfig }) => {
  const isConnected = !!config.CLICKUP_OAUTH_TOKEN;

  // jank hack: prevent layout shift, parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="✓ ClickUp Account Connected"
          secondaryMessage="Your ClickUp account is connected and tasks will be ingested."
        />
      )}

      <WarningMessage
        primaryMessage={'⚠️ Oauth Limitations'}
        secondaryMessage={
          <>
            Grapevine syncs <em>only</em> tasks visible to the connected user.
          </>
        }
      />
      {isConnected ? <Reconnect /> : <Connect />}
    </Flex>
  );
};

const Reconnect = () => {
  const {
    mutate: handleConnect,
    isPending: isConnectPending,
    isSuccess: isConnectSuccess,
    error: connectError,
  } = useOauthClickup();
  const {
    mutate: disconnectClickup,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectClickup();

  // waiting to redirect on isConnectSuccess;
  const isLoading = isConnectPending || isDisconnectPending || isConnectSuccess;
  const error = connectError || disconnectError;

  return (
    <Flex direction="column" gap={12}>
      <Flex gap={8}>
        <Button onClick={() => handleConnect()} kind="primary" loading={isLoading} size="sm">
          Reconnect
        </Button>
        <Button onClick={() => disconnectClickup()} loading={isLoading} kind="danger" size="sm">
          Disconnect
        </Button>
      </Flex>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

const Connect = () => {
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthClickup();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => handleConnect()}
        kind="primary"
        size="sm"
        loading={isPending || isSuccess}
        style={{ alignSelf: 'start' }}
      >
        Connect
      </Button>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

const ErrorComponent = ({ error }: { error: Error }) => (
  <Flex direction="column" gap={8}>
    <Text color="dangerPrimary" fontWeight="semibold">
      Error Connecting ClickUp: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
    </Text>
  </Flex>
);

const WarningMessage = ({
  primaryMessage,
  secondaryMessage,
}: {
  primaryMessage: ReactNode;
  secondaryMessage: ReactNode;
}) => (
  <Flex
    direction="column"
    gap={8}
    style={{
      padding: '12px',
      backgroundColor: '#fff4e5',
      borderRadius: '8px',
      border: '1px solid #ffe4cc',
    }}
  >
    <Text fontSize="sm" color="warningPrimary" fontWeight="semibold">
      {primaryMessage}
    </Text>
    <Text fontSize="sm" color="secondary">
      {secondaryMessage}
    </Text>
  </Flex>
);

const SuccessMessage = ({
  primaryMessage,
  secondaryMessage,
}: {
  primaryMessage: ReactNode;
  secondaryMessage: ReactNode;
}) => (
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
      {primaryMessage}
    </Text>
    <Text fontSize="sm" color="secondary">
      {secondaryMessage}
    </Text>
  </Flex>
);

export { ClickupOauth };
