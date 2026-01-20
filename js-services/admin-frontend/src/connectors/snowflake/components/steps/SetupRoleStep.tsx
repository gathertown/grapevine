import type { FC } from 'react';
import { Flex, Text, Input } from '@gathertown/gather-design-system';
import { CodeBlock } from '../../../../components/shared/CodeBlock';

interface SetupRoleStepProps {
  roleSetupSql: string;
  securityIntegrationSql: string;
  accountIdentifier: string;
  onAccountIdentifierChange: (value: string) => void;
}

export const SetupRoleStep: FC<SetupRoleStepProps> = ({
  roleSetupSql,
  securityIntegrationSql,
  accountIdentifier,
  onAccountIdentifierChange,
}) => (
  <Flex direction="column" gap={16}>
    <Flex direction="column" gap={8}>
      <Text fontSize="md" fontWeight="semibold">
        Step 1: Create a Role with Query Permissions
      </Text>
      <Text fontSize="sm" color="secondary">
        Run these SQL commands in Snowflake to create a role with the necessary permissions:
      </Text>
      <CodeBlock code={roleSetupSql} />
    </Flex>

    <Flex direction="column" gap={8}>
      <Text fontSize="md" fontWeight="semibold">
        Step 2: Create OAuth Security Integration
      </Text>
      <Text fontSize="sm" color="secondary">
        Run this SQL command to create the OAuth integration (requires <strong>ACCOUNTADMIN</strong>{' '}
        role or <strong>CREATE INTEGRATION</strong> privilege):
      </Text>
      <CodeBlock code={securityIntegrationSql} />
    </Flex>

    <Flex direction="column" gap={8}>
      <Text fontSize="sm" fontWeight="semibold">
        Snowflake Account Identifier
      </Text>
      <Input
        placeholder="myorg-account123"
        value={accountIdentifier}
        onChange={(e) => onAccountIdentifierChange(e.target.value)}
      />
      <Text fontSize="xs" color="secondary">
        Find this in your Snowflake account URL (e.g., myorg-account123.snowflakecomputing.com)
      </Text>
    </Flex>
  </Flex>
);
