import { memo, useState, useEffect } from 'react';
import type { FC } from 'react';
import { Flex, Text, ToggleSwitch, Button } from '@gathertown/gather-design-system';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useAuth } from '../hooks/useAuth';
import { ProactivitySettings } from './ProactivitySettings';
import { useAllConfig, useSetConfigValue, connectorConfigQueryKey } from '../api/config';
import { apiClient } from '../api/client';

interface SlackAppInfo {
  isLegacy: boolean;
  slackAppId: string | null;
  teamDomain: string | null;
}

const fetchSlackAppInfo = (): Promise<SlackAppInfo> =>
  apiClient.get<SlackAppInfo>('/api/slack/app-info');

const SlackBotSettings: FC = memo(() => {
  const queryClient = useQueryClient();
  const { data: configData } = useAllConfig();
  const { mutateAsync: updateConfigValue } = useSetConfigValue();
  const { trackEvent } = useTrackEvent();
  const { user } = useAuth();
  const [skipExternalGuests, setSkipExternalGuests] = useState(false);
  const [skipMentionsByNonMembers, setSkipMentionsByNonMembers] = useState(true);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [saveStates, setSaveStates] = useState({
    skipExternalGuests: false,
    skipMentionsByNonMembers: false,
  });

  const { data: slackAppInfo } = useQuery({
    queryKey: ['slack-app-info'],
    queryFn: fetchSlackAppInfo,
  });

  const canShowRenameLink =
    slackAppInfo && !slackAppInfo.isLegacy && slackAppInfo.slackAppId && slackAppInfo.teamDomain;

  const renameSlackAppUrl = canShowRenameLink
    ? `https://${slackAppInfo.teamDomain}.slack.com/marketplace/${slackAppInfo.slackAppId}-grapevine?next_id=0&tab=settings`
    : null;

  // Initialize state from config data
  useEffect(() => {
    setSkipExternalGuests(configData?.SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS === 'true');
    setSkipMentionsByNonMembers(
      configData?.SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS !== 'false' // Default true
    );
  }, [configData]);

  const saveSkipExternalGuests = async (enabled: boolean) => {
    setSaveStates((prev) => ({ ...prev, skipExternalGuests: true }));

    try {
      await updateConfigValue({
        key: 'SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS',
        value: enabled ? 'true' : 'false',
      });

      trackEvent('external_guest_setting_changed', {
        user_id: user?.id,
        skip_external_guests: enabled,
      });
    } catch (err) {
      console.error('Failed to save skip external guests setting:', err);
    } finally {
      setSaveStates((prev) => ({ ...prev, skipExternalGuests: false }));
    }
  };

  const saveSkipMentionsByNonMembers = async (enabled: boolean) => {
    setSaveStates((prev) => ({ ...prev, skipMentionsByNonMembers: true }));

    try {
      await updateConfigValue({
        key: 'SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS',
        value: enabled ? 'true' : 'false',
      });

      trackEvent('skip_mentions_by_non_members_changed', {
        user_id: user?.id,
        skip_mentions_by_non_members: enabled,
      });
    } catch (err) {
      console.error('Failed to save skip mentions by non-members setting:', err);
    } finally {
      setSaveStates((prev) => ({ ...prev, skipMentionsByNonMembers: false }));
    }
  };

  const handleReconnect = async () => {
    try {
      const response = await apiClient.get<{ url: string }>('/api/slack/install');
      window.location.href = response.url;
    } catch (error) {
      console.error('Error getting Slack OAuth URL:', error);
    }
  };

  const handleDisconnect = async () => {
    if (
      !confirm(
        'Are you sure you want to disconnect Slack? This will remove the bot from your workspace.'
      )
    ) {
      return;
    }

    setIsDisconnecting(true);
    try {
      await apiClient.delete('/api/slack/disconnect');
      await queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    } catch (error) {
      console.error('Failed to disconnect Slack:', error);
    } finally {
      setIsDisconnecting(false);
    }
  };

  return (
    <Flex direction="column" width="100%" style={{ gap: 44 }} maxWidth="600px">
      {/* External Users Section */}
      <Flex direction="column" gap={16}>
        <Text fontSize="lg" color="primary" fontWeight="semibold">
          External Users
        </Text>

        {/* Proactive Responses */}
        <Flex direction="row" justify="space-between" align="flex-start" width="100%" gap={12}>
          <Flex direction="column" gap={4} style={{ flex: 1 }}>
            <Text fontWeight="medium">
              Skip proactive responses in channels with external users
            </Text>
            <Text color="tertiary">
              When enabled, the bot will not respond proactively (without being mentioned) in
              channels that contain guest users or are Slack Connect channels.
            </Text>
          </Flex>
          <ToggleSwitch
            checked={skipExternalGuests}
            onChange={async (e) => {
              setSkipExternalGuests(e.target.checked);
              await saveSkipExternalGuests(e.target.checked);
            }}
            disabled={saveStates.skipExternalGuests}
          />
        </Flex>

        {/* Skip Mentions by Non-Members */}
        <Flex direction="row" justify="space-between" align="flex-start" width="100%" gap={12}>
          <Flex direction="column" gap={4} style={{ flex: 1 }}>
            <Text fontWeight="medium">Skip @mentions from external users</Text>
            <Text color="tertiary">
              When enabled, the bot will not respond to @mentions from guest users or users from
              other Slack workspaces (Slack Connect). Internal team members can still @mention the
              bot in any channel. Recommended for security.
            </Text>
          </Flex>
          <ToggleSwitch
            checked={skipMentionsByNonMembers}
            onChange={async (e) => {
              setSkipMentionsByNonMembers(e.target.checked);
              await saveSkipMentionsByNonMembers(e.target.checked);
            }}
            disabled={saveStates.skipMentionsByNonMembers}
          />
        </Flex>
      </Flex>

      {/* Proactivity Section */}
      <ProactivitySettings />

      {/* Connection Management Section */}
      <Flex direction="column" gap={16}>
        <Text fontSize="lg" color="primary" fontWeight="semibold">
          Connection
        </Text>
        <Text color="tertiary">
          Reconnect to refresh your Slack connection or disconnect the bot from your workspace. To
          completely remove the bot from your workspace,{' '}
          <a
            href="https://slack.com/help/articles/360003125231-Remove-apps-and-custom-integrations-from-your-workspace"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'inherit', textDecoration: 'underline' }}
          >
            follow these instructions
          </a>
          .
        </Text>
        <Flex direction="row" gap={8}>
          <Button onClick={handleReconnect} kind="secondary" size="sm">
            Reconnect Slack
          </Button>
          <Button
            onClick={handleDisconnect}
            kind="danger"
            size="sm"
            loading={isDisconnecting}
            disabled={isDisconnecting}
          >
            Disconnect
          </Button>
          {renameSlackAppUrl && (
            <a
              href={renameSlackAppUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: 'none' }}
            >
              <Button kind="secondary" size="sm">
                Rename Slack App
              </Button>
            </a>
          )}
        </Flex>
      </Flex>
    </Flex>
  );
});

SlackBotSettings.displayName = 'SlackBotSettings';

export { SlackBotSettings };
