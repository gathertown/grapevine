import { memo, useCallback, useEffect, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text } from '@gathertown/gather-design-system';
import { SlackOAuthSetupCard } from '../SlackOAuthSetupCard';
import { SlackBotSettings } from '../SlackBotSettings';
import { useAllConfig } from '../../api/config';

const OnboardingSlackPage: FC = memo(() => {
  const { isLoading } = useAllConfig();
  const navigate = useNavigate();
  const [isInSetupFlow] = useState(true);

  const handleSetupComplete = useCallback(() => {
    // User completed Slack OAuth and configured proactivity, redirect to home
    navigate('/');
  }, [navigate]);

  // Listen for OAuth progress messages from popup
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) {
        return;
      }

      if (event.data.type === 'SLACK_AUTH_COMPLETE') {
        // OAuth completed (success or error) - popup has closed, user can continue
        // No action needed, user will manually click "Complete Setup"
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, []);

  if (isLoading) {
    return (
      <Flex direction="column" width="100%" maxWidth="800px" mx="auto" px={24}>
        <Flex direction="column" gap={8} mb={32}>
          <Text fontSize="md" color="tertiary">
            Loading configuration...
          </Text>
        </Flex>
      </Flex>
    );
  }

  // Show setup card if in setup flow (regardless of configuration status)
  if (isInSetupFlow) {
    return (
      <Flex direction="column" width="100%" maxWidth="800px" mx="auto">
        <SlackOAuthSetupCard onComplete={handleSetupComplete} />
      </Flex>
    );
  }

  // Show settings only after user has completed setup flow
  return (
    <Flex direction="column" width="100%" maxWidth="800px" mx="auto">
      <SlackBotSettings />
    </Flex>
  );
});

OnboardingSlackPage.displayName = 'OnboardingSlackPage';

export { OnboardingSlackPage };
