import { ReactNode, useState } from 'react';
import {
  Box,
  Button,
  Flex,
  IconButton,
  Input,
  RadioGroup,
  Text,
} from '@gathertown/gather-design-system';
import { AsanaConfig } from '../asanaConfig';
import {
  useDisconnectAsanaOauth,
  useDisconnectAsanaServiceAccount,
  useOauthAsana,
  useSaveAsanaServiceAccountToken,
} from '../asanaApi';
import { Link } from '../../../components/shared';
import { DOCS_URL, getSupportContactText } from '../../../constants';

type AsanaPlanTier = 'enterprise' | 'other';

const AsanaConnectStep = ({ config }: { config: AsanaConfig }) => {
  const isServiceAccountConnected = !!config.ASANA_SERVICE_ACCOUNT_TOKEN;
  const isOauthConnected = !!config.ASANA_OAUTH_TOKEN_PAYLOAD;
  const isConnected = isServiceAccountConnected || isOauthConnected;

  const initialSelectedTier: AsanaPlanTier | '' = isServiceAccountConnected
    ? 'enterprise'
    : isOauthConnected
      ? 'other'
      : '';
  const [selectedTier, setSelectedTier] = useState<AsanaPlanTier | ''>(initialSelectedTier);
  const options = [
    { label: 'Enterprise', value: 'enterprise' },
    { label: 'Starter or Advanced', value: 'other' },
  ];

  // jank hack: prevent layout shift, parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="✓ Asana Account Connected"
          secondaryMessage="Your Asana account is connected and tasks will be ingested."
        />
      )}

      <Box
        borderColor="tertiary"
        borderWidth={1}
        borderStyle="solid"
        borderRadius={8}
        style={{ padding: '12px' }}
      >
        <RadioGroup
          name="Asana Plan"
          items={options}
          label="Select your Asana Tier"
          value={selectedTier ?? ''}
          onChange={(value) => setSelectedTier(value as AsanaPlanTier)}
        />
      </Box>

      {selectedTier === 'enterprise' && <ServiceAccountConnect config={config} />}
      {selectedTier === 'other' && <OauthConnect config={config} />}
    </Flex>
  );
};

const ServiceAccountConnect = ({ config }: { config: AsanaConfig }) => {
  const {
    mutate: saveToken,
    isPending: isConnecting,
    error: connectError,
  } = useSaveAsanaServiceAccountToken();
  const {
    mutate: disconnectAsana,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectAsanaServiceAccount();

  const [asanaServiceAccountToken, setAsanaServiceAccountToken] = useState<string>(
    config.ASANA_SERVICE_ACCOUNT_TOKEN ?? ''
  );
  const [keyVisible, setKeyVisible] = useState(false);

  const isConnected = config.ASANA_SERVICE_ACCOUNT_TOKEN;
  const isPending = isConnecting || isDisconnecting;
  const error = connectError || disconnectError;

  return (
    <>
      <InfoMessage
        primaryMessage="Grapevine only reads data"
        secondaryMessage={
          <>
            Asana service accounts are either SCIM only or full access.
            {DOCS_URL && (
              <>
                <br />
                <br />
                <Link
                  href={`${DOCS_URL}/connectors/asana`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  See our documentation for details.
                </Link>
              </>
            )}
          </>
        }
      />
      <div>
        <Text>
          <ol>
            <li>
              <Link
                href="https://app.asana.com/admin/0/apps/serviceaccounts"
                target="_blank"
                rel="noopener noreferrer"
              >
                Create a "Full permissions" service account
              </Link>
            </li>
            <li>Copy and paste the token below to connect</li>
          </ol>
        </Text>
      </div>

      <Flex gap={2}>
        <div style={{ flexGrow: 1 }}>
          <Input
            label="Asana Service Account Token"
            placeholder="2/0000000000000000/0000000000000000:ffffffffffffffffffffffffffffffff"
            value={asanaServiceAccountToken}
            onChange={(e) => setAsanaServiceAccountToken(e.target.value)}
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
          onClick={() => saveToken(asanaServiceAccountToken)}
          kind="primary"
          size="sm"
          loading={isPending}
          disabled={
            asanaServiceAccountToken.length === 0 ||
            config.ASANA_SERVICE_ACCOUNT_TOKEN === asanaServiceAccountToken
          }
        >
          Connect
        </Button>
        {isConnected && (
          <Button
            onClick={() =>
              disconnectAsana(undefined, { onSuccess: () => setAsanaServiceAccountToken('') })
            }
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

const OauthConnect = ({ config }: { config: AsanaConfig }) => {
  const isOauthConnected = !!config.ASANA_OAUTH_TOKEN_PAYLOAD;
  return (
    <>
      <WarningMessage
        primaryMessage={'⚠️ Oauth Limitations'}
        secondaryMessage={
          <>
            Grapevine syncs <em>only</em> tasks visible to the connected user.
          </>
        }
      />
      <InfoMessage
        primaryMessage="Grapevine only reads data"
        secondaryMessage={
          <>
            Some Asana resources are not available via scoped permissions.
            {DOCS_URL && (
              <>
                <br />
                <br />
                <Link
                  href={`${DOCS_URL}/connectors/asana`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  See our documentation for details.
                </Link>
              </>
            )}
          </>
        }
      />
      {isOauthConnected ? <Reconnect /> : <Connect />}
    </>
  );
};

const Reconnect = () => {
  const {
    mutate: handleConnect,
    isPending: isConnectPending,
    isSuccess: isConnectSuccess,
    error: connectError,
  } = useOauthAsana();
  const {
    mutate: disconnectAsana,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectAsanaOauth();

  // waiting to redirect on isConnectSuccess;
  const isLoading = isConnectPending || isDisconnectPending || isConnectSuccess;
  const error = connectError || disconnectError;

  return (
    <Flex direction="column" gap={12}>
      <Flex gap={8}>
        <Button onClick={() => handleConnect()} kind="primary" loading={isLoading} size="sm">
          Reconnect
        </Button>
        <Button onClick={() => disconnectAsana()} loading={isLoading} kind="danger" size="sm">
          Disconnect
        </Button>
      </Flex>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

const Connect = () => {
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthAsana();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => handleConnect()}
        kind="primary"
        size="sm"
        loading={isPending || isSuccess}
        style={{ alignSelf: 'start' }}
      >
        Connect
      </Button>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

const ErrorComponent = ({ error }: { error: Error }) => (
  <Flex direction="column" gap={8}>
    <Text color="dangerPrimary" fontWeight="semibold">
      Error Connecting Asana: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
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

const InfoMessage = ({
  primaryMessage,
  secondaryMessage,
}: {
  primaryMessage: ReactNode;
  secondaryMessage?: ReactNode;
}) => (
  <Flex
    direction="column"
    gap={8}
    style={{
      padding: '12px',
      backgroundColor: '#d1ecf1',
      borderRadius: '8px',
      border: '1px solid #bee5eb',
    }}
  >
    <Text fontSize="sm" color="primary" fontWeight="semibold">
      {primaryMessage}
    </Text>
    {secondaryMessage && (
      <Text fontSize="sm" color="secondary">
        {secondaryMessage}
      </Text>
    )}
  </Flex>
);

export { AsanaConnectStep };
