import { ReactNode, useEffect, useState } from 'react';
import { Button, Flex, Input, Text } from '@gathertown/gather-design-system';

import zendeskSubdomainScreenshot from '../../assets/zendesk-subdomain-step1.png';
import { useDisconnectZendesk, useOauthZendesk } from '../../zendeskApi';
import { ZendeskConfig } from '../../zendeskConfig';
import { getSupportContactText } from '../../../../constants';

const ConnectStep = ({ config }: { config: ZendeskConfig }) => {
  const [zendeskSubdomain, setZendeskSubdomain] = useState<string>(config.ZENDESK_SUBDOMAIN ?? '');

  // Keep local state in sync with config changes
  useEffect(() => {
    setZendeskSubdomain(config.ZENDESK_SUBDOMAIN ?? '');
  }, [config.ZENDESK_SUBDOMAIN]);

  const isConnected = !!config.ZENDESK_TOKEN_PAYLOAD;

  return (
    <Flex direction="column" gap={16}>
      {isConnected ? (
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
            ✓ Zendesk Account Connected
          </Text>
          <Text fontSize="sm" color="secondary">
            Your Zendesk account is connected and tickets will be ingested.
          </Text>
        </Flex>
      ) : (
        <Text>Connect your Zendesk account to sync support tickets with Grapevine.</Text>
      )}

      <Warning
        primaryMessage={'⚠️ Ticket Visibility'}
        secondaryMessage={
          <>
            <strong>All</strong> tickets synced from Zendesk will be visible to everyone in
            Grapevine.
          </>
        }
      />

      <Warning
        primaryMessage={'⚠️ Admin Required'}
        secondaryMessage={
          <>Grapevine uses admin-only APIs. Please ensure an administrator authorizes below.</>
        }
      />

      <img
        src={zendeskSubdomainScreenshot}
        alt="Subdomain in Account, Branding, Appearance settings"
        style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
      />
      <Flex align="center" gap="4px">
        <Input
          placeholder="mycompany"
          value={zendeskSubdomain}
          onChange={(e) => setZendeskSubdomain(e.target.value)}
          autoComplete="off"
          data-form-type="other"
          data-lpignore="true"
          data-1p-ignore="true"
        />
        <Text fontSize="md">.zendesk.com</Text>
      </Flex>

      {isConnected ? (
        <Reconnect subdomain={zendeskSubdomain} />
      ) : (
        <Connect subdomain={zendeskSubdomain} />
      )}
    </Flex>
  );
};

interface ReconnectProps {
  subdomain: string;
}

const Reconnect = ({ subdomain }: ReconnectProps) => {
  const {
    mutate: handleConnect,
    isPending: isConnectPending,
    isSuccess: isConnectSuccess,
    error: connectError,
  } = useOauthZendesk();
  const {
    mutate: disconnectZendesk,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectZendesk();

  // waiting to redirect on isConnectSuccess;
  const isLoading = isConnectPending || isDisconnectPending || isConnectSuccess;

  const error = connectError || disconnectError;

  return (
    <Flex direction="column" gap={12}>
      <Flex gap={8}>
        <Button
          onClick={() => handleConnect(subdomain)}
          kind="primary"
          loading={isLoading}
          disabled={subdomain.trim() === ''}
          size="sm"
        >
          Reconnect
        </Button>
        <Button onClick={() => disconnectZendesk()} loading={isLoading} kind="danger" size="sm">
          Disconnect
        </Button>
      </Flex>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

interface ConnectProps {
  subdomain: string;
}

const Connect = ({ subdomain }: ConnectProps) => {
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthZendesk();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => handleConnect(subdomain)}
        kind="primary"
        size="sm"
        loading={isPending || isSuccess}
        disabled={subdomain.trim() === ''}
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
      Error Initiating Zendesk OAuth: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
    </Text>
  </Flex>
);

const Warning = ({
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

export { ConnectStep };
