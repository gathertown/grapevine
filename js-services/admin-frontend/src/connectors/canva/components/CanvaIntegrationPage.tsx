import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { SetupHeader } from '../../../components/shared/SetupHeader';
import { Integration } from '../../../types';
import { CanvaConfig } from '../canvaConfig';
import { CanvaOauth } from './CanvaOauth';

const CanvaIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();

  const [searchParams] = useSearchParams();
  const oauthSuccessParam = searchParams.get('success') === 'true';
  const oauthError = searchParams.get('error') === 'true';

  const integration = integrations.find((int) => int.id === 'canva');

  const isConnected = !!configData?.CANVA_ACCESS_TOKEN;
  const oauthSuccess = oauthSuccessParam && isConnected;

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
        <Text>Loading Canva configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading Canva configuration</Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      <Button
        onClick={() => navigate('/integrations')}
        kind="secondary"
        size="sm"
        style={{ alignSelf: 'flex-start' }}
      >
        &larr; Back to Integrations
      </Button>
      <CanvaIntegration integration={integration} config={configData} />
      {oauthSuccess && (
        <Text fontSize="md" color="successPrimary">
          Canva connected successfully! Your designs will begin syncing shortly.
        </Text>
      )}
      {oauthError && (
        <Text fontSize="md" color="dangerPrimary">
          Canva connection failed. Please try again.
        </Text>
      )}
    </Flex>
  );
};

interface CanvaIntegrationProps {
  integration: Integration;
  config: CanvaConfig;
}

const CanvaIntegration = ({ config, integration }: CanvaIntegrationProps) => {
  return (
    <Flex direction="column" gap={24}>
      <SetupHeader
        title={`Set up ${integration.name}`}
        primaryIcon={<integration.Icon size={48} />}
        showGrapevine
        showConnection
      />
      <Flex direction="column" gap={16}>
        <CanvaOauth config={config} />
      </Flex>
    </Flex>
  );
};

export { CanvaIntegrationPage };
