import type { FC } from 'react';
import { Flex, Text, Input, Select, IconButton } from '@gathertown/gather-design-system';
import { Link } from '../../../../components/shared';
import { POSTHOG_HOSTS } from '../../posthogConfig';

interface CredentialsStepProps {
  hostOption: string;
  onHostOptionChange: (value: string) => void;
  customHost: string;
  onCustomHostChange: (value: string) => void;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  keyVisible: boolean;
  onToggleKeyVisible: () => void;
  disabled?: boolean;
}

export const CredentialsStep: FC<CredentialsStepProps> = ({
  hostOption,
  onHostOptionChange,
  customHost,
  onCustomHostChange,
  apiKey,
  onApiKeyChange,
  keyVisible,
  onToggleKeyVisible,
  disabled = false,
}) => {
  return (
    <Flex direction="column" gap={16}>
      <Flex direction="column" gap={12}>
        <Text>
          <ol>
            <li>
              Go to your{' '}
              <Link
                href="https://us.posthog.com/settings/user-api-keys"
                target="_blank"
                rel="noopener noreferrer"
              >
                PostHog Personal API Keys settings
              </Link>{' '}
              (Settings &rarr; Personal API Keys)
            </li>
            <li>Click &quot;+ Create personal API key&quot; and give it a label</li>
            <li>
              Select the following <strong>read-only scopes</strong>:
            </li>
          </ol>
        </Text>
        <Flex
          direction="column"
          gap={4}
          style={{
            marginLeft: '32px',
            padding: '12px',
            backgroundColor: '#f5f5f5',
            borderRadius: '6px',
            fontFamily: 'monospace',
            fontSize: '13px',
          }}
        >
          <Text fontSize="sm">annotation:read</Text>
          <Text fontSize="sm">dashboard:read</Text>
          <Text fontSize="sm">experiment:read</Text>
          <Text fontSize="sm">feature_flag:read</Text>
          <Text fontSize="sm">insight:read</Text>
          <Text fontSize="sm">project:read</Text>
          <Text fontSize="sm">query:read (for analytics queries)</Text>
          <Text fontSize="sm">survey:read</Text>
          <Text fontSize="sm">user:read (for account verification)</Text>
        </Flex>
        <Text>
          <ol start={4}>
            <li>Copy the API key immediately (you won&apos;t see it again!)</li>
            <li>Paste it below and select your PostHog host</li>
          </ol>
        </Text>
      </Flex>

      <Flex direction="column" gap={12}>
        <Text fontWeight="semibold">PostHog Host</Text>
        <Select
          label=""
          options={POSTHOG_HOSTS}
          placeholder="Select PostHog host"
          value={hostOption}
          onChange={(value) => onHostOptionChange(value)}
          disabled={disabled}
        />

        {hostOption === 'custom' && (
          <Input
            label="Custom Host URL"
            placeholder="https://your-posthog-instance.com"
            value={customHost}
            onChange={(e) => onCustomHostChange(e.target.value)}
            disabled={disabled}
          />
        )}
      </Flex>

      <Flex gap={2}>
        <div style={{ flexGrow: 1 }}>
          <Input
            label="Personal API Key"
            placeholder="phx_..."
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            disabled={disabled}
            type={keyVisible ? 'text' : 'password'}
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
          />
        </div>
        <IconButton
          icon={keyVisible ? 'eyeClosed' : 'eye'}
          onClick={onToggleKeyVisible}
          aria-label={keyVisible ? 'Hide API key' : 'Show API key'}
          size="md"
          kind="transparent"
          style={{ alignSelf: 'flex-end' }}
        />
      </Flex>
    </Flex>
  );
};
