import type { FC } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

interface ConnectedStateProps {
  accountIdentifier: string;
  onDisconnect: () => void;
  isDisconnecting: boolean;
  disconnectError: Error | null;
}

export const ConnectedState: FC<ConnectedStateProps> = ({
  accountIdentifier,
  onDisconnect,
  isDisconnecting,
  disconnectError,
}) => (
  <Flex direction="column" gap={16}>
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
        Snowflake Account Connected
      </Text>
      <Text fontSize="sm" color="secondary">
        Your Snowflake account ({accountIdentifier}) is connected.
      </Text>
    </Flex>

    <Flex direction="column" gap={8}>
      <Text fontSize="sm" color="secondary">
        To reconnect with a different account, disconnect first.
      </Text>
      <Flex gap={8}>
        <Button onClick={onDisconnect} loading={isDisconnecting} kind="danger" size="sm">
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
);
