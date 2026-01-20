import type { FC } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { SUPPORT_EMAIL } from '../../../../constants';

interface ConnectStepProps {
  onConnect: () => void;
  isLoading: boolean;
  error: Error | null;
  oauthErrorMessage: string | null;
}

export const ConnectStep: FC<ConnectStepProps> = ({
  onConnect,
  isLoading,
  error,
  oauthErrorMessage,
}) => (
  <Flex direction="column" gap={16}>
    <Text fontSize="sm" color="secondary">
      Connect your Snowflake account to query data with natural language.
    </Text>

    <Text fontSize="sm" color="secondary">
      Click the button below to connect your Snowflake account. You'll be redirected to Snowflake to
      authorize the connection.
    </Text>

    <Button onClick={onConnect} kind="primary" loading={isLoading} disabled={isLoading} fullWidth>
      {isLoading ? 'Redirecting to Snowflake...' : 'Connect Snowflake'}
    </Button>

    {(error || oauthErrorMessage) && (
      <Flex direction="column" gap={8}>
        <Text color="dangerPrimary" fontWeight="semibold">
          Error Initiating Snowflake OAuth: {error?.message || oauthErrorMessage}
        </Text>
        <Text fontSize="sm" color="secondary">
          Please verify your account identifier and try again, or contact {SUPPORT_EMAIL}
        </Text>
      </Flex>
    )}
  </Flex>
);
