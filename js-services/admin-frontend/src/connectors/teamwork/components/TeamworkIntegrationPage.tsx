import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { SetupHeader } from '../../../components/shared/SetupHeader';
import { Integration } from '../../../types';
import { TeamworkConfig } from '../teamworkConfig';
import { TeamworkOauth } from './TeamworkOauth';

const TeamworkIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();

  const [searchParams] = useSearchParams();
  const oauthSuccessParam = searchParams.get('success') === 'true';
  const oauthError = searchParams.get('error') === 'true';

  const integration = integrations.find((int) => int.id === 'teamwork');

  const isConnected = !!configData?.TEAMWORK_ACCESS_TOKEN;
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
        <Text>Loading Teamwork configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading Teamwork configuration</Text>
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
      <TeamworkIntegration integration={integration} config={configData} />
      {oauthSuccess && (
        <Text fontSize="md" color="successPrimary">
          Teamwork connected successfully! Your tasks will begin syncing shortly.
        </Text>
      )}
      {oauthError && (
        <Text fontSize="md" color="dangerPrimary">
          Teamwork connection failed. Please try again.
        </Text>
      )}
    </Flex>
  );
};

interface TeamworkIntegrationProps {
  integration: Integration;
  config: TeamworkConfig;
}

const TeamworkIntegration = ({ config, integration }: TeamworkIntegrationProps) => {
  return (
    <Flex direction="column" gap={24}>
      <SetupHeader
        title={`Set up ${integration.name}`}
        primaryIcon={<integration.Icon size={48} />}
        showGrapevine
        showConnection
      />
      <Flex direction="column" gap={16}>
        <TeamworkOauth config={config} />
      </Flex>
    </Flex>
  );
};

export { TeamworkIntegrationPage };
