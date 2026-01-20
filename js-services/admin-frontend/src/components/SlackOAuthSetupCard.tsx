import { memo } from 'react';
import type { FC } from 'react';
import { Flex, Text, Button } from '@gathertown/gather-design-system';
import { apiClient } from '../api/client';
import { SetupHeader } from './shared';
import { SlackIcon } from '../assets/icons';
import { ProactivitySettings } from './ProactivitySettings';
import { useAllConfig } from '../api/config';

interface SlackOAuthSetupCardProps {
  onComplete: () => void;
}

const SlackOAuthSetupCard: FC<SlackOAuthSetupCardProps> = memo(({ onComplete }) => {
  const { data: configData } = useAllConfig();

  // Check if already installed (has bot token)
  const installationStatus = configData?.SLACK_BOT_TOKEN ? 'success' : 'pending';

  const handleInstallClick = async () => {
    try {
      const response = await apiClient.get<{ url: string }>('/api/slack/install');
      // Redirect to Slack OAuth (full page redirect, not popup)
      window.location.href = response.url;
    } catch (error) {
      console.error('Error getting Slack OAuth URL:', error);
      // Error will be shown in console; user can retry by clicking button again
    }
  };

  if (installationStatus === 'success') {
    return (
      <Flex direction="column" width="100%" maxWidth="700px" mx="auto" px={24}>
        <SetupHeader primaryIcon={<SlackIcon size={48} />} title="Slack Connected!" />

        <Flex direction="column" gap={24} mt={32}>
          <Flex direction="column" gap={16}>
            <Text fontSize="md" fontWeight="semibold">
              ✅ Bot Successfully Installed
            </Text>
            <Text fontSize="sm" color="secondary">
              Your Slack bot has been successfully installed! Before continuing, configure how the
              bot should behave in your workspace.
            </Text>
          </Flex>

          {/* Proactivity Settings */}
          <Flex direction="column" gap={16} mt={16}>
            <ProactivitySettings />
          </Flex>

          <Flex justify="flex-end" mt={32}>
            <Button onClick={onComplete} kind="primary">
              Continue to Home
            </Button>
          </Flex>
        </Flex>
      </Flex>
    );
  }

  return (
    <Flex direction="column" width="100%" maxWidth="700px" mx="auto" px={24}>
      <SetupHeader primaryIcon={<SlackIcon size={48} />} title="Connect Slack" />

      <Flex direction="column" gap={32} mt={32}>
        <Flex direction="column" gap={16}>
          <Text fontSize="sm" color="secondary">
            Click the button below to install the Grapevine bot to your Slack workspace. You'll be
            redirected to Slack to authorize the app.
          </Text>
        </Flex>

        <Flex>
          <Button onClick={handleInstallClick} fullWidth kind="primary">
            Connect Slack Workspace
          </Button>
        </Flex>
      </Flex>
    </Flex>
  );
});

SlackOAuthSetupCard.displayName = 'SlackOAuthSetupCard';

export { SlackOAuthSetupCard };
