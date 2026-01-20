import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useIntegrations } from '../../../contexts/IntegrationsContext';
import { useAllConfig } from '../../../api/config';
import { PostHogIntegration } from './PostHogIntegration';

const PostHogIntegrationPage = () => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();
  const { error, isLoading } = useAllConfig();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const integration = integrations.find((int) => int.id === 'posthog');

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
        <Text>Loading PostHog configuration...</Text>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <Text color="dangerPrimary">Error loading PostHog configuration</Text>
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
      <PostHogIntegration
        integration={integration}
        isModalOpen={isModalOpen}
        onModalOpenChange={setIsModalOpen}
        renderInline={true}
      />
    </Flex>
  );
};

export { PostHogIntegrationPage };
