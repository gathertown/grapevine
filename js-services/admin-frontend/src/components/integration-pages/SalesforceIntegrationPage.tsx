import { memo } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Flex } from '@gathertown/gather-design-system';
import { SalesforceIntegration } from '../integrations/SalesforceIntegration';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { useIntegrationComplete } from '../../hooks/useIntegrationComplete';
import { SALESFORCE_ENABLED } from '../../constants';
import { checkIfWeShouldStartAnsweringSampleQuestions } from '../../utils/sampleQuestions';

const SalesforceIntegrationPage: FC = memo(() => {
  const navigate = useNavigate();
  const { integrations } = useIntegrations();

  // Call hook before any conditional returns
  const handleComplete = useIntegrationComplete(() => {
    checkIfWeShouldStartAnsweringSampleQuestions();
  });

  // Redirect to home if Salesforce is not enabled
  if (!SALESFORCE_ENABLED) {
    navigate('/');
    return null;
  }

  const integration = integrations.find((int) => int.id === 'salesforce');

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
      <SalesforceIntegration
        integration={integration}
        isModalOpen={true} // Required by component but not used in inline mode
        onModalOpenChange={() => {}} // No-op for inline mode
        renderInline={true}
        onComplete={handleComplete}
      />
    </Flex>
  );
});

SalesforceIntegrationPage.displayName = 'SalesforceIntegrationPage';

export { SalesforceIntegrationPage };
