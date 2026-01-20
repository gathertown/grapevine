import type { FC } from 'react';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { GitLabIntegration } from './GitLabIntegration';

const GitLabIntegrationPage: FC = () => {
  const { integrations } = useIntegrations();
  const gitlabIntegration = integrations.find((i) => i.id === 'gitlab');

  if (!gitlabIntegration) {
    return null;
  }

  return (
    <GitLabIntegration
      integration={gitlabIntegration}
      isModalOpen={false}
      onModalOpenChange={() => {}}
      renderInline={true}
    />
  );
};

export { GitLabIntegrationPage };
