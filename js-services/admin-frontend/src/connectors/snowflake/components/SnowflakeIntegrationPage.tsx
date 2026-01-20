import { useNavigate } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { SnowflakeConfig } from '../snowflakeConfig';
import { SnowflakeIntegration } from './SnowflakeIntegration';
import { SemanticModelsStep } from './SemanticModelsStep';
import { useSnowflakeStatus } from '../snowflakeApi';

const SnowflakeIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();
  const { data: status } = useSnowflakeStatus();

  const integration = integrations.find((int) => int.id === 'snowflake');
  const isConnected = status?.connected ?? false;

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
        <Text>Loading Snowflake configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading Snowflake configuration</Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      <SnowflakeIntegration
        integration={integration}
        isModalOpen={true}
        onModalOpenChange={() => {}}
        renderInline={true}
      />
      {isConnected && <SemanticModelsStep config={configData as SnowflakeConfig} />}
    </Flex>
  );
};

export { SnowflakeIntegrationPage };
