import type { FC } from 'react';
import { Flex, Text, Input } from '@gathertown/gather-design-system';
import { CodeBlock } from '../../../../components/shared/CodeBlock';

interface CustomEndpointsStepProps {
  retrieveEndpointsSql: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  onAuthorizationEndpointChange: (value: string) => void;
  onTokenEndpointChange: (value: string) => void;
}

export const CustomEndpointsStep: FC<CustomEndpointsStepProps> = ({
  retrieveEndpointsSql,
  authorizationEndpoint,
  tokenEndpoint,
  onAuthorizationEndpointChange,
  onTokenEndpointChange,
}) => (
  <Flex direction="column" gap={16}>
    <Flex direction="column" gap={8}>
      <Text fontSize="md" fontWeight="semibold">
        Retrieve OAuth Endpoints (Optional - for Private Link or custom vanity URLs)
      </Text>
      <Text fontSize="sm" color="secondary">
        If you're using Private Link or custom vanity URLs, retrieve your OAuth endpoints:
      </Text>
      <CodeBlock code={retrieveEndpointsSql} />
      <Text fontSize="xs" color="secondary">
        Look for the <strong>OAUTH_AUTHORIZATION_ENDPOINT</strong> and{' '}
        <strong>OAUTH_TOKEN_ENDPOINT</strong> fields in the response. If using standard Snowflake
        URLs, you can skip this step.
      </Text>
    </Flex>

    <Flex direction="column" gap={8}>
      <Text fontSize="sm" fontWeight="semibold">
        OAuth Authorization Endpoint (Optional)
      </Text>
      <Input
        placeholder="https://example.privatelink.snowflakecomputing.com/oauth/authorize"
        value={authorizationEndpoint}
        onChange={(e) => onAuthorizationEndpointChange(e.target.value)}
      />
      <Text fontSize="xs" color="secondary">
        Only needed for Private Link or custom vanity URLs. Leave empty to use standard Snowflake
        OAuth endpoint.
      </Text>
    </Flex>

    <Flex direction="column" gap={8}>
      <Text fontSize="sm" fontWeight="semibold">
        OAuth Token Endpoint (Optional)
      </Text>
      <Input
        placeholder="https://example.privatelink.snowflakecomputing.com/oauth/token-request"
        value={tokenEndpoint}
        onChange={(e) => onTokenEndpointChange(e.target.value)}
      />
      <Text fontSize="xs" color="secondary">
        Only needed for Private Link or custom vanity URLs. Leave empty to use standard Snowflake
        OAuth endpoint.
      </Text>
    </Flex>
  </Flex>
);
