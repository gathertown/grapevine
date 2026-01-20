import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { SetupHeader } from '../../../components/shared/SetupHeader';
import { AsanaConfig } from '../asanaConfig';
import { Integration } from '../../../types';
import { AsanaConnectStep } from './asanaSteps';

const AsanaIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();

  const [searchParams] = useSearchParams();
  const oauthErrorMessage = searchParams.get('oauth-error');

  const integration = integrations.find((int) => int.id === 'asana');

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
        <Text>Loading Asana configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading Asana configuration</Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      <AsanaIntegration integration={integration} config={configData} />
      {oauthErrorMessage && (
        <Text fontSize="md" color="dangerPrimary">
          ❌ Asana connection failed: {oauthErrorMessage}
        </Text>
      )}
    </Flex>
  );
};

interface AsanaIntegrationProps {
  integration: Integration;
  config: AsanaConfig;
}

const AsanaIntegration = ({ config, integration }: AsanaIntegrationProps) => {
  return (
    <Flex direction="column" gap={24}>
      <SetupHeader
        title={`Set up ${integration.name}`}
        primaryIcon={<integration.Icon size={48} />}
        showGrapevine
        showConnection
      />
      <Flex direction="column" gap={16}>
        <AsanaConnectStep config={config} />
      </Flex>
    </Flex>
  );
};

export { AsanaIntegrationPage };
