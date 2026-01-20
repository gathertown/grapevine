import { useState } from 'react';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { JiraIntegration } from '../integrations/JiraIntegration';

export const JiraIntegrationPage = () => {
  const { integrations } = useIntegrations();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Find the Jira integration from the list
  const jiraIntegration = integrations.find((integration) => integration.id === 'jira');

  if (!jiraIntegration) {
    return null;
  }

  const handleModalOpenChange = (open: boolean) => {
    setIsModalOpen(open);
  };

  return (
    <JiraIntegration
      integration={jiraIntegration}
      isModalOpen={isModalOpen}
      onModalOpenChange={handleModalOpenChange}
      renderInline={true}
    />
  );
};
