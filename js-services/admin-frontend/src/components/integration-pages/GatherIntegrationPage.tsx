import { memo } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex } from '@gathertown/gather-design-system';
import { GatherIntegration } from '../integrations/GatherIntegration';
import { useIntegrations } from '../../contexts/IntegrationsContext';

const GatherIntegrationPage: FC = memo(() => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();

  const integration = integrations.find((int) => int.id === 'gather');

  if (!integration) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <div>Integration not found</div>
        <Button onClick={() => navigate('/integrations')}>Back to Integrations</Button>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      {/* Integration Component */}
      <GatherIntegration integration={integration} />
    </Flex>
  );
});

GatherIntegrationPage.displayName = 'GatherIntegrationPage';

export { GatherIntegrationPage };
