import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';

import { useIntegrations } from '../../../../contexts/IntegrationsContext';
import { ZendeskIntegration } from './ZendeskIntegration';
import { useAllConfig } from '../../../../api/config';

const ZendeskIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { data: configData, error, isLoading } = useAllConfig();

  const [searchParams] = useSearchParams();
  const oauthErrorMessage = searchParams.get('oauth-error');

  const integration = integrations.find((int) => int.id === 'zendesk');

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
        <Text>Loading Zendesk configuration...</Text>
      </Flex>
    );
  }

  if (error || !configData) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading Zendesk configuration</Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      <ZendeskIntegration integration={integration} config={configData} />
      {oauthErrorMessage && (
        <Text fontSize="md" color="dangerPrimary">
          ❌ Zendesk connection failed: {oauthErrorMessage}
        </Text>
      )}
    </Flex>
  );
};

export { ZendeskIntegrationPage };
