import type { FC } from 'react';
import { BaseIntegration } from './BaseIntegration';
import type { Integration } from '../../types';
import { Flex, Text } from '@gathertown/gather-design-system';
import gatherHomePage from '../../assets/setup-screenshots/gather-homepage.png';
import aiConfigSettings from '../../assets/setup-screenshots/configure-ai-settings.png';
import { Link } from 'react-router-dom';
interface GatherIntegrationProps {
  integration: Integration;
}

export const GatherIntegration: FC<GatherIntegrationProps> = ({ integration }) => {
  const isConnected = false;
  const steps = [
    {
      title: 'Connect to Gather',
      content: (
        <Flex direction="column" gap={16}>
          <Text>Connect your Gather account to sync meeting data with Grapevine.</Text>

          {isConnected ? (
            <Flex direction="column" gap={12} align="center">
              <Text color="successPrimary">✓ Gather is connected</Text>
              <Text fontSize="sm" color="secondary">
                Your Gather account is successfully connected and indexing data.
              </Text>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              <Flex direction="column" gap={4}>
                <Text>
                  1. Log in to{' '}
                  <a href="https://app.v2.gather.town" target="_blank" rel="noopener noreferrer">
                    Gather
                  </a>
                  . Select the space you'd like to collect data from:
                </Text>

                <img
                  src={gatherHomePage}
                  alt="Integration capabilities settings with read-only selected"
                  style={{ width: '100%', borderRadius: 8 }}
                />
              </Flex>

              <Flex direction="column" gap={4}>
                <Text>
                  2. Click "Configure AI" to set up the integration and enable data syncing:
                </Text>

                <img
                  src={aiConfigSettings}
                  alt="Integration capabilities settings with read-only selected"
                  style={{ width: '100%', borderRadius: 8 }}
                />
              </Flex>

              <Text>
                After completing these steps, you may return <Link to="/">home</Link>.
              </Text>
            </Flex>
          )}
        </Flex>
      ),
    },
  ];
  return (
    <BaseIntegration
      integration={integration}
      steps={steps}
      isModalOpen={false}
      onModalOpenChange={() => {}}
      currentStepIndex={0}
      onStepChange={() => {}}
      isStepValid={() => true}
      onComplete={async () => {}}
      renderStepContent={(step) => (typeof step.content === 'function' ? null : step.content)}
      renderInline
    />
  );
};
