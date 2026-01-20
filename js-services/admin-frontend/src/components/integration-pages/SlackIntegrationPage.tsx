import { memo } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex } from '@gathertown/gather-design-system';
import { SlackIntegration } from '../integrations/SlackIntegration';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { useIntegrationComplete } from '../../hooks/useIntegrationComplete';

const SlackIntegrationPage: FC = memo(() => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();

  const integration = integrations.find((int) => int.id === 'slack');

  // Note: We don't call checkIfWeShouldStartAnsweringSampleQuestions for Slack exports
  const handleComplete = useIntegrationComplete();

  if (!integration) {
    return (
      <Flex direction="column" gap={16} maxWidth="800px" mx="auto">
        <div>Integration not found</div>
        <Button onClick={() => navigate('/')}>Back to Home</Button>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={24} maxWidth="800px" mx="auto">
      {/* Integration Component */}
      <SlackIntegration
        integration={integration}
        isModalOpen={true} // Required by component but not used in inline mode
        onModalOpenChange={() => {}} // No-op for inline mode
        renderInline={true}
        onComplete={handleComplete}
      />
    </Flex>
  );
});

SlackIntegrationPage.displayName = 'SlackIntegrationPage';

export { SlackIntegrationPage };
