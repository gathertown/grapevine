import type { FC } from 'react';
import { Flex, Text, Button } from '@gathertown/gather-design-system';

interface ConnectedStateProps {
  host: string;
  onDisconnect: () => void;
  isDisconnecting: boolean;
  disconnectError: Error | null;
}

export const ConnectedState: FC<ConnectedStateProps> = ({
  host,
  onDisconnect,
  isDisconnecting,
  disconnectError,
}) => {
  return (
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
          PostHog Account Connected
        </Text>
        <Text fontSize="sm" color="secondary">
          Your PostHog account is connected and dashboards, insights, feature flags, experiments,
          and surveys will be ingested.
        </Text>
      </Flex>

      <Flex direction="column" gap={8}>
        <Text fontSize="sm" color="secondary">
          Connected to: <strong>{host}</strong>
        </Text>
      </Flex>

      <Flex gap={8}>
        <Button onClick={onDisconnect} loading={isDisconnecting} kind="danger" size="sm">
          Disconnect
        </Button>
      </Flex>

      {disconnectError && (
        <Flex direction="column" gap={8}>
          <Text color="dangerPrimary" fontWeight="semibold">
            Error Disconnecting: {disconnectError.message}
          </Text>
        </Flex>
      )}
    </Flex>
  );
};
