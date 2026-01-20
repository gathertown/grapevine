import { memo, useEffect } from 'react';
import type { FC } from 'react';
import { Flex, SegmentedControl } from '@gathertown/gather-design-system';
import { StatsPage } from './StatsPage';
import { SlackBotSettings } from './SlackBotSettings';
import { Initializing } from './Initializing';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { isSlackBotConfigured } from '../utils';
import { useAllConfig } from '../api/config';

type PageMode = 'stats' | 'settings';

const SlackBotAppPage: FC = memo(() => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: configData } = useAllConfig();
  const navigate = useNavigate();

  // Get current tab from URL, default to 'stats'
  const tab = searchParams.get('tab');
  const mode: PageMode = tab === 'settings' ? 'settings' : 'stats';

  const needsSlackbotSetup = !!configData && !isSlackBotConfigured(configData);

  // Only redirect after initialization is complete and we're sure step1 is incomplete
  useEffect(() => {
    if (needsSlackbotSetup) {
      navigate('/onboarding/slack');
    }
  }, [needsSlackbotSetup, navigate]);

  const handleTabChange = (value: string) => {
    setSearchParams(value === 'stats' ? {} : { tab: value });
  };

  // Show loading while initializing
  if (!configData) {
    return <Initializing />;
  }
  return (
    <Flex direction="column" gap={24} width="100%">
      <Flex width="100%">
        <SegmentedControl
          key={mode} // Force re-render when mode changes from URL
          segments={[
            { label: 'Stats', value: 'stats' },
            { label: 'Settings', value: 'settings' },
          ]}
          defaultValue={mode}
          onSegmentChange={handleTabChange}
        />
      </Flex>

      {mode === 'stats' ? <StatsPage /> : <SlackBotSettings />}
    </Flex>
  );
});

SlackBotAppPage.displayName = 'SlackBotAppPage';

export { SlackBotAppPage };
