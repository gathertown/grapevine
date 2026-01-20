import { ReactNode, useState } from 'react';
import { Button, Flex, IconButton, Input, Text } from '@gathertown/gather-design-system';
import { FirefliesConfig } from '../firefliesConfig';
import { useConnectFireflies, useDisconnectFireflies } from '../firefliesApi';
import { Link } from '../../../components/shared';
import { getSupportContactText } from '../../../constants';

const FirefliesConnectStep = ({ config }: { config: FirefliesConfig }) => {
  const isConnected = !!config.FIREFLIES_API_KEY;

  // jank hack: prevent layout shift, parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="✓ Fireflies Account Connected"
          secondaryMessage="Your Fireflies account is connected and transcripts will be ingested."
        />
      )}

      <ApiKeyConnect config={config} />
    </Flex>
  );
};

const ApiKeyConnect = ({ config }: { config: FirefliesConfig }) => {
  const { mutate: connect, isPending: isConnecting, error: connectError } = useConnectFireflies();
  const {
    mutate: disconnect,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectFireflies();

  const [firefliesApiKey, setFirefliesApiKey] = useState<string>(config.FIREFLIES_API_KEY ?? '');
  const [keyVisible, setKeyVisible] = useState(false);

  const isConnected = !!config.FIREFLIES_API_KEY;
  const isPending = isConnecting || isDisconnecting;
  const error = connectError || disconnectError;

  return (
    <>
      <div>
        <Text>
          <ol>
            <li>
              <Link
                href="https://guide.fireflies.ai/articles/7734409426-learn-about-the-super-admin-role#api-and-automation-scope"
                target="_blank"
                rel="noopener noreferrer"
              >
                Create a "Super Admin" account
              </Link>
            </li>
            <li>
              <Link
                href="https://app.fireflies.ai/settings#DeveloperSettings"
                target="_blank"
                rel="noopener noreferrer"
              >
                Copy your API key
              </Link>{' '}
              and paste below to connect
            </li>
          </ol>
        </Text>
      </div>
      <WarningMessage
        primaryMessage="Non Super Admin Limitations"
        secondaryMessage="If you cannot create or use a Super Admin account then only transcripts available to the api key below will be ingested."
      />

      <Flex gap={2}>
        <div style={{ flexGrow: 1 }}>
          <Input
            label="Fireflies API Key"
            placeholder="00000000-ffff-4fff-ffff-000000000000"
            value={firefliesApiKey}
            onChange={(e) => setFirefliesApiKey(e.target.value)}
            disabled={isPending}
            type={keyVisible ? 'text' : 'password'}
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
          />
        </div>
        <IconButton
          icon={keyVisible ? 'eyeClosed' : 'eye'}
          onClick={() => setKeyVisible((prev) => !prev)}
          aria-label={keyVisible ? 'Hide token' : 'Show token'}
          size="md" // same size as input height 32px
          kind="transparent"
          style={{ alignSelf: 'flex-end' }}
        />
      </Flex>

      <Flex gap={8}>
        <Button
          onClick={() => connect(firefliesApiKey)}
          kind="primary"
          size="sm"
          loading={isPending}
          disabled={firefliesApiKey.length === 0 || config.FIREFLIES_API_KEY === firefliesApiKey}
        >
          Connect
        </Button>
        {isConnected && (
          <Button
            onClick={() => disconnect(undefined, { onSuccess: () => setFirefliesApiKey('') })}
            loading={isPending}
            kind="danger"
            size="sm"
          >
            Disconnect
          </Button>
        )}
      </Flex>
      {error && <ErrorComponent error={error} />}
    </>
  );
};

const ErrorComponent = ({ error }: { error: Error }) => (
  <Flex direction="column" gap={8}>
    <Text color="dangerPrimary" fontWeight="semibold">
      Error Connecting Fireflies: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
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

const WarningMessage = ({
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
      backgroundColor: '#fff4e5',
      borderRadius: '8px',
      border: '1px solid #ffe4cc',
    }}
  >
    <Text fontSize="sm" color="warningPrimary" fontWeight="semibold">
      {primaryMessage}
    </Text>
    <Text fontSize="sm" color="secondary">
      {secondaryMessage}
    </Text>
  </Flex>
);

export { FirefliesConnectStep };
