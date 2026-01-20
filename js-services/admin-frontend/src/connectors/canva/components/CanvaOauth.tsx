import { ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useDisconnectCanva, useOauthCanva } from '../canvaApi';
import { CanvaConfig } from '../canvaConfig';
import { getSupportContactText } from '../../../constants';

const CanvaOauth = ({ config }: { config: CanvaConfig }) => {
  const isConnected = !!config.CANVA_ACCESS_TOKEN;
  const userDisplayName = config.CANVA_USER_DISPLAY_NAME;

  // Prevent layout shift - parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Canva Account Connected"
          secondaryMessage={
            userDisplayName
              ? `Connected as ${userDisplayName}. Your designs will begin syncing shortly.`
              : 'Your Canva account is connected and designs will be synced.'
          }
        />
      )}

      <InfoMessage
        primaryMessage={'Data Access'}
        secondaryMessage={
          <>
            Grapevine will sync designs from your Canva account. Design titles, descriptions, and
            metadata will be indexed for search.
          </>
        }
      />
      {isConnected ? <Disconnect /> : <Connect />}
    </Flex>
  );
};

const Disconnect = () => {
  const {
    mutate: disconnectCanva,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectCanva();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => disconnectCanva()}
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
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthCanva();

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
      Error Connecting Canva: {error.message}
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

export { CanvaOauth };
