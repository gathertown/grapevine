import type { FC } from 'react';
import { Flex, Text, Icon } from '@gathertown/gather-design-system';
import { CodeBlock } from '../../../../components/shared/CodeBlock';
import type { CredentialsValidationState } from './types';

interface RetrieveCredentialsStepProps {
  retrieveCredentialsSql: string;
  credentialsJson: string;
  onCredentialsJsonChange: (value: string) => void;
  credentialsValidation: CredentialsValidationState;
}

export const RetrieveCredentialsStep: FC<RetrieveCredentialsStepProps> = ({
  retrieveCredentialsSql,
  credentialsJson,
  onCredentialsJsonChange,
  credentialsValidation,
}) => (
  <Flex direction="column" gap={16}>
    <Flex direction="column" gap={8}>
      <Text fontSize="md" fontWeight="semibold">
        Retrieve OAuth Credentials
      </Text>
      <Text fontSize="sm" color="secondary">
        Run this SQL command to get your Client ID and Secret:
      </Text>
      <CodeBlock code={retrieveCredentialsSql} />
    </Flex>

    <Flex direction="column" gap={8}>
      <Flex justify="space-between" align="center">
        <Text fontSize="sm" fontWeight="semibold">
          Quick Setup: Paste OAuth Credentials (Optional)
        </Text>
        {credentialsJson.trim() && (
          <Flex align="center" gap={4}>
            <Icon
              name={credentialsValidation.isValid ? 'check' : 'close'}
              size="sm"
              color={credentialsValidation.isValid ? 'successPrimary' : 'dangerPrimary'}
            />
            <Text
              fontSize="xs"
              color={credentialsValidation.isValid ? 'successPrimary' : 'dangerPrimary'}
              fontWeight="semibold"
            >
              {credentialsValidation.isValid ? 'valid' : 'invalid'}
            </Text>
          </Flex>
        )}
      </Flex>
      <textarea
        placeholder={`Paste the JSON output from: SELECT SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('your_integration_name');

Example:
{
  "OAUTH_CLIENT_ID": "AbCdEf123456==",
  "OAUTH_CLIENT_SECRET": "XyZ789aBcDeF123456=="
}`}
        value={credentialsJson}
        onChange={(e) => onCredentialsJsonChange(e.target.value)}
        rows={6}
        style={{
          width: '100%',
          padding: '8px',
          fontSize: '14px',
          fontFamily: 'monospace',
          border: `2px solid ${
            !credentialsJson.trim()
              ? '#dee2e6'
              : credentialsValidation.isValid
                ? '#28a745'
                : '#dc3545'
          }`,
          borderRadius: '4px',
          resize: 'vertical',
          backgroundColor: '#ffffff',
          color: '#333333',
        }}
      />
      <Text fontSize="xs" color="secondary">
        Paste the JSON output from SYSTEM$SHOW_OAUTH_CLIENT_SECRETS to auto-fill Client ID and
        Secret below
      </Text>
      {credentialsValidation.error && (
        <Text fontSize="xs" color="dangerPrimary">
          {credentialsValidation.error}
        </Text>
      )}
    </Flex>
  </Flex>
);
