import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { SetupHeader } from '../../../components/shared/SetupHeader';
import { Integration } from '../../../types';
import { ClickupConfig } from '../clickupConfig';
import { ClickupOauth } from './ClickupOauth';

const ClickupIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();

  const [searchParams] = useSearchParams();
  const oauthErrorMessage = searchParams.get('oauth-error');

  const integration = integrations.find((int) => int.id === 'clickup');

  if (!integration) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <div>Integration not found</div>
        <Button onClick={() => navigate('/')}>Back to Home</Button>
      </Flex>
    );
  }

  if (isLoading) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text>Loading ClickUp configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading ClickUp configuration</Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      <ClickupIntegration integration={integration} config={configData} />
      {oauthErrorMessage && (
        <Text fontSize="md" color="dangerPrimary">
          ❌ ClickUp connection failed: {oauthErrorMessage}
        </Text>
      )}
    </Flex>
  );
};

interface ClickupIntegrationProps {
  integration: Integration;
  config: ClickupConfig;
}

const ClickupIntegration = ({ config, integration }: ClickupIntegrationProps) => {
  return (
    <Flex direction="column" gap={24}>
      <SetupHeader
        title={`Set up ${integration.name}`}
        primaryIcon={<integration.Icon size={48} />}
        showGrapevine
        showConnection
      />
      <Flex direction="column" gap={16}>
        <ClickupOauth config={config} />
      </Flex>
    </Flex>
  );
};

export { ClickupIntegrationPage };
