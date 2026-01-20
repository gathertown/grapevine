import { useState } from 'react';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { ConfluenceIntegration } from '../integrations/ConfluenceIntegration';

export const ConfluenceIntegrationPage = () => {
  const { integrations } = useIntegrations();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Find the Confluence integration from the list
  const confluenceIntegration = integrations.find((integration) => integration.id === 'confluence');

  if (!confluenceIntegration) {
    return null;
  }

  const handleModalOpenChange = (open: boolean) => {
    setIsModalOpen(open);
  };

  return (
    <ConfluenceIntegration
      integration={confluenceIntegration}
      isModalOpen={isModalOpen}
      onModalOpenChange={handleModalOpenChange}
      renderInline={true}
    />
  );
};
