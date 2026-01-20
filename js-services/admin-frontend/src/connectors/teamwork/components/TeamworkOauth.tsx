import { ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useDisconnectTeamwork, useOauthTeamwork } from '../teamworkApi';
import { TeamworkConfig } from '../teamworkConfig';
import { getSupportContactText } from '../../../constants';

const TeamworkOauth = ({ config }: { config: TeamworkConfig }) => {
  const isConnected = !!config.TEAMWORK_ACCESS_TOKEN;
  const userName = config.TEAMWORK_USER_NAME;

  // Prevent layout shift - parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Teamwork Account Connected"
          secondaryMessage={
            userName
              ? `Connected as ${userName}. Your tasks will begin syncing shortly.`
              : 'Your Teamwork account is connected and tasks will be synced.'
          }
        />
      )}

      <InfoMessage
        primaryMessage={'Data Access'}
        secondaryMessage={
          <>
            Grapevine will sync tasks from your Teamwork projects. Task titles, descriptions, and
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
    mutate: disconnectTeamwork,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectTeamwork();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => disconnectTeamwork()}
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
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthTeamwork();

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
      Error Connecting Teamwork: {error.message}
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

export { TeamworkOauth };
