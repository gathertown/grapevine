import { memo, useEffect } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex } from '@gathertown/gather-design-system';
import { SlackBotSettings } from './SlackBotSettings';
import { Initializing } from './Initializing';
import { isSlackBotConfigured } from '../utils';
import { useAllConfig } from '../api/config';

const SlackBotPage: FC = memo(() => {
  const { data: configData } = useAllConfig();
  const navigate = useNavigate();

  const needsSlackbotSetup = !!configData && !isSlackBotConfigured(configData);

  // Only redirect after initialization is complete and we're sure step1 is incomplete
  useEffect(() => {
    if (needsSlackbotSetup) {
      navigate('/onboarding/slack');
    }
  }, [needsSlackbotSetup, navigate]);

  // Show loading while initializing
  if (!configData) {
    return <Initializing />;
  }

  // If `needsSlackbotSetup`, we'll redirect (handled by useEffect above)
  // Return null to avoid flashing content before redirect
  if (needsSlackbotSetup) {
    return null;
  }

  // Show settings if step 1 is complete
  return (
    <Flex direction="column" width="100%" maxWidth="800px" mx="auto">
      <SlackBotSettings />
    </Flex>
  );
});

SlackBotPage.displayName = 'SlackBotPage';

export { SlackBotPage };
