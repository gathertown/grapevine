import { memo } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex } from '@gathertown/gather-design-system';
import { GongIntegration } from '../integrations/GongIntegration';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { useIntegrationComplete } from '../../hooks/useIntegrationComplete';
import { checkIfWeShouldStartAnsweringSampleQuestions } from '../../utils/sampleQuestions';

const GongIntegrationPage: FC = memo(() => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();

  const integration = integrations.find((int) => int.id === 'gong');

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
      <GongIntegration
        integration={integration}
        isModalOpen={true}
        onModalOpenChange={() => {}}
        renderInline={true}
        onComplete={handleComplete}
      />
    </Flex>
  );
});

GongIntegrationPage.displayName = 'GongIntegrationPage';

export { GongIntegrationPage };
