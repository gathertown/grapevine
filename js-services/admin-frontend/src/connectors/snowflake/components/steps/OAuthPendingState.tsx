import type { FC } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';

export const OAuthPendingState: FC = () => (
  <Flex direction="column" gap={16} align="center" justify="center" style={{ padding: '48px 0' }}>
    <Flex
      direction="column"
      gap={8}
      align="center"
      style={{
        padding: '24px',
        backgroundColor: '#e3f2fd',
        borderRadius: '8px',
        border: '1px solid #90caf9',
        textAlign: 'center',
      }}
    >
      <Text fontSize="md" fontWeight="semibold">
        Connecting to Snowflake...
      </Text>
      <Text fontSize="sm" color="secondary">
        Please wait while we complete the OAuth connection.
      </Text>
    </Flex>
  </Flex>
);
