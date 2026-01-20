import { memo } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex } from '@gathertown/gather-design-system';
import { NotionIntegration } from '../integrations/NotionIntegration';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { useIntegrationComplete } from '../../hooks/useIntegrationComplete';
import { checkIfWeShouldStartAnsweringSampleQuestions } from '../../utils/sampleQuestions';

const NotionIntegrationPage: FC = memo(() => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();

  const integration = integrations.find((int) => int.id === 'notion');

  const handleComplete = useIntegrationComplete(() => {
    checkIfWeShouldStartAnsweringSampleQuestions();
  });

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
      <NotionIntegration
        integration={integration}
        isModalOpen={true} // Required by component but not used in inline mode
        onModalOpenChange={() => {}} // No-op for inline mode
        renderInline={true}
        onComplete={handleComplete}
      />
    </Flex>
  );
});

NotionIntegrationPage.displayName = 'NotionIntegrationPage';

export { NotionIntegrationPage };
