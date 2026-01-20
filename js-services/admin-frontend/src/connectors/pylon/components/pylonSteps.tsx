import { ReactNode, useState } from 'react';
import { Button, Flex, IconButton, Input, Text } from '@gathertown/gather-design-system';
import { PylonConfig } from '../pylonConfig';
import { useConnectPylon, useDisconnectPylon } from '../pylonApi';
import { Link } from '../../../components/shared';
import { getSupportContactText } from '../../../constants';

const PylonConnectStep = ({ config }: { config: PylonConfig }) => {
  const isConnected = !!config.PYLON_API_KEY;

  // jank hack: prevent layout shift, parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Pylon Account Connected"
          secondaryMessage="Your Pylon account is connected and support issues will be ingested."
        />
      )}

      <ApiKeyConnect config={config} />
    </Flex>
  );
};

const ApiKeyConnect = ({ config }: { config: PylonConfig }) => {
  const { mutate: connect, isPending: isConnecting, error: connectError } = useConnectPylon();
  const {
    mutate: disconnect,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectPylon();

  const [pylonApiKey, setPylonApiKey] = useState<string>(config.PYLON_API_KEY ?? '');
  const [keyVisible, setKeyVisible] = useState(false);

  const isConnected = !!config.PYLON_API_KEY;
  const isPending = isConnecting || isDisconnecting;
  const error = connectError || disconnectError;

  return (
    <>
      <div>
        <Text>
          <ol>
            <li>
              Go to your{' '}
              <Link
                href="https://app.usepylon.com/settings/api-tokens"
                target="_blank"
                rel="noopener noreferrer"
              >
                Pylon API Settings
              </Link>
            </li>
            <li>Generate an API token with read access</li>
            <li>Copy the token and paste it below to connect</li>
          </ol>
        </Text>
      </div>

      <Flex gap={2}>
        <div style={{ flexGrow: 1 }}>
          <Input
            label="Pylon API Token"
            placeholder="pylon_api_..."
            value={pylonApiKey}
            onChange={(e) => setPylonApiKey(e.target.value)}
            disabled={isPending || isConnected}
            type={keyVisible ? 'text' : 'password'}
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
          />
        </div>
        {!isConnected && (
          <IconButton
            icon={keyVisible ? 'eyeClosed' : 'eye'}
            onClick={() => setKeyVisible((prev) => !prev)}
            aria-label={keyVisible ? 'Hide token' : 'Show token'}
            size="md" // same size as input height 32px
            kind="transparent"
            style={{ alignSelf: 'flex-end' }}
          />
        )}
      </Flex>

      <Flex gap={8}>
        {!isConnected && (
          <Button
            onClick={() => connect(pylonApiKey)}
            kind="primary"
            size="sm"
            loading={isPending}
            disabled={pylonApiKey.length === 0}
          >
            Connect
          </Button>
        )}
        {isConnected && (
          <Button
            onClick={() => disconnect(undefined, { onSuccess: () => setPylonApiKey('') })}
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
      Error Connecting Pylon: {error.message}
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

export { PylonConnectStep };
