import { ReactNode } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useDisconnectPipedrive, useOauthPipedrive } from '../pipedriveApi';
import { PipedriveConfig } from '../pipedriveConfig';
import { getSupportContactText } from '../../../constants';

const PipedriveOauth = ({ config }: { config: PipedriveConfig }) => {
  const isConnected = !!config.PIPEDRIVE_ACCESS_TOKEN;
  const companyName = config.PIPEDRIVE_COMPANY_NAME;

  // Prevent layout shift - parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Pipedrive Account Connected"
          secondaryMessage={
            companyName
              ? `Connected to ${companyName}. Your deals, contacts, organizations, and activities will be synced.`
              : 'Your Pipedrive account is connected and data will be synced.'
          }
        />
      )}

      <InfoMessage
        primaryMessage={'Data Access'}
        secondaryMessage={
          <>
            Grapevine will sync deals, persons (contacts), organizations, activities, and notes
            visible to the connected user.
          </>
        }
      />
      {isConnected ? <Disconnect /> : <Connect />}
    </Flex>
  );
};

const Disconnect = () => {
  const {
    mutate: disconnectPipedrive,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectPipedrive();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => disconnectPipedrive()}
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
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthPipedrive();

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
      Error Connecting Pipedrive: {error.message}
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

export { PipedriveOauth };
