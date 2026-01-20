import { ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useDisconnectMonday, useOauthMonday } from '../mondayApi';
import { MondayConfig } from '../mondayConfig';
import { getSupportContactText } from '../../../constants';

const MondayOauth = ({ config }: { config: MondayConfig }) => {
  const isConnected = !!config.MONDAY_ACCESS_TOKEN;

  // Prevent layout shift - parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Monday.com Account Connected"
          secondaryMessage="Your Monday.com account is connected and boards, items, and updates will be synced."
        />
      )}

      <InfoMessage
        primaryMessage={'Data Access'}
        secondaryMessage={
          <>
            Grapevine will sync boards, items (tasks), and updates (comments) visible to the
            connected user.
          </>
        }
      />
      {isConnected ? <Disconnect /> : <Connect />}
    </Flex>
  );
};

const Disconnect = () => {
  const {
    mutate: disconnectMonday,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectMonday();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => disconnectMonday()}
        loading={isDisconnectPending}
        kind="danger"
        size="sm"
        style={{ alignSelf: 'start' }}
      >
        Disconnect
      </Button>
      {disconnectError && <ErrorComponent error={disconnectError} />}
    </Flex>
  );
};

const Connect = () => {
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthMonday();

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
      Error Connecting Monday.com: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
    </Text>
  </Flex>
);

const InfoMessage = ({
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
      backgroundColor: '#f0f9ff',
      borderRadius: '8px',
      border: '1px solid #bae6fd',
    }}
  >
    <Text fontSize="sm" color="primary" fontWeight="semibold">
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

export { MondayOauth };
