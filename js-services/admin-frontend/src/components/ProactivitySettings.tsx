import { memo, useState, useEffect, useCallback, useRef } from 'react';
import type { FC } from 'react';
import { Flex, Text, Input, Button, ToggleSwitch, Slider } from '@gathertown/gather-design-system';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useAuth } from '../hooks/useAuth';
import { useAllConfig, useSetConfigValue } from '../api/config';

const DEFAULT_CONFIDENCE_THRESHOLD = 70;

const ProactivitySettings: FC = memo(() => {
  const { data: configData } = useAllConfig();
  const { mutateAsync: updateConfigValue } = useSetConfigValue();
  const { trackEvent } = useTrackEvent();
  const { user } = useAuth();
  const [proactivityEnabled, setProactivityEnabled] = useState(false);
  const [excludedChannels, setExcludedChannels] = useState('');
  const [allowedChannels, setAllowedChannels] = useState('');
  const [confidenceThreshold, setConfidenceThreshold] = useState(DEFAULT_CONFIDENCE_THRESHOLD);
  const [saveStates, setSaveStates] = useState({
    proactivityToggle: false,
    channelSettings: false,
  });
  const confidenceThresholdTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize state from config data
  useEffect(() => {
    setProactivityEnabled(configData?.SLACK_BOT_QA_ALL_CHANNELS === 'true');
    setExcludedChannels(configData?.SLACK_BOT_QA_DISALLOWED_CHANNELS || '');
    setAllowedChannels(configData?.SLACK_BOT_QA_ALLOWED_CHANNELS || '');
    const threshold = parseInt(configData?.SLACK_BOT_QA_CONFIDENCE_THRESHOLD || '');
    if (!isNaN(threshold)) {
      setConfidenceThreshold(threshold);
    }
  }, [configData]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (confidenceThresholdTimeoutRef.current) {
        clearTimeout(confidenceThresholdTimeoutRef.current);
      }
    };
  }, []);

  const saveProactivityToggle = async (enabled: boolean) => {
    setSaveStates((prev) => ({ ...prev, proactivityToggle: true }));

    try {
      await updateConfigValue({
        key: 'SLACK_BOT_QA_ALL_CHANNELS',
        value: enabled ? 'true' : 'false',
      });

      // Track answer proactively setting change
      trackEvent('answer_proactively_setting_changed', {
        user_id: user?.id,
        proactively_enabled: enabled,
      });
    } catch (err) {
      console.error('Failed to save proactivity setting:', err);
    } finally {
      setSaveStates((prev) => ({ ...prev, proactivityToggle: false }));
    }
  };

  const saveChannelSettings = async () => {
    setSaveStates((prev) => ({ ...prev, channelSettings: true }));

    try {
      if (proactivityEnabled) {
        // When proactivity is ON, save excluded channels (blocklist)
        await updateConfigValue({
          key: 'SLACK_BOT_QA_DISALLOWED_CHANNELS',
          value: excludedChannels.trim(),
        });

        // Parse channels and track blocklist update
        const channelList = excludedChannels.trim()
          ? excludedChannels
              .split(',')
              .map((c) => c.trim())
              .filter((c) => c.length > 0)
          : [];
        trackEvent('proactive_channels_blocklist_updated', {
          user_id: user?.id,
          channels: channelList,
          channel_count: channelList.length,
        });
      } else {
        // When proactivity is OFF, save allowed channels (allowlist)
        await updateConfigValue({
          key: 'SLACK_BOT_QA_ALLOWED_CHANNELS',
          value: allowedChannels.trim(),
        });

        // Parse channels and track allowlist update
        const channelList = allowedChannels.trim()
          ? allowedChannels
              .split(',')
              .map((c) => c.trim())
              .filter((c) => c.length > 0)
          : [];
        trackEvent('proactive_channels_allowlist_updated', {
          user_id: user?.id,
          channels: channelList,
          channel_count: channelList.length,
        });
      }
    } catch (err) {
      console.error('Failed to save channel settings:', err);
    } finally {
      setSaveStates((prev) => ({ ...prev, channelSettings: false }));
    }
  };

  const saveConfidenceThreshold = useCallback(
    async (threshold: number) => {
      try {
        await updateConfigValue({
          key: 'SLACK_BOT_QA_CONFIDENCE_THRESHOLD',
          value: threshold.toString(),
        });

        // Track confidence threshold setting change
        trackEvent('proactive_confidence_threshold_changed', {
          user_id: user?.id,
          confidence_threshold: threshold,
        });
      } catch (err) {
        console.error('Failed to save confidence threshold:', err);
      }
    },
    [updateConfigValue, trackEvent, user?.id]
  );

  // Debounced save function for confidence threshold
  const debouncedSaveConfidenceThreshold = useCallback(
    (threshold: number) => {
      // Clear existing timeout
      if (confidenceThresholdTimeoutRef.current) {
        clearTimeout(confidenceThresholdTimeoutRef.current);
      }

      // Set new timeout to save after 500ms of no changes
      confidenceThresholdTimeoutRef.current = setTimeout(() => {
        saveConfidenceThreshold(threshold);
        confidenceThresholdTimeoutRef.current = null;
      }, 500);
    },
    [saveConfidenceThreshold]
  );

  // Handler for confidence threshold changes
  const handleConfidenceThresholdChange = useCallback(
    (value: number) => {
      setConfidenceThreshold(value);
      debouncedSaveConfidenceThreshold(value);
    },
    [debouncedSaveConfidenceThreshold]
  );

  return (
    <Flex direction="column" gap={8}>
      <Text fontSize="lg" color="primary" fontWeight="semibold">
        Proactivity
      </Text>
      <Flex direction="column" width="100%" gap={24} align="flex-start">
        {/* Proactivity Toggle */}
        <Flex direction="row" justify="space-between" align="flex-start" width="100%" gap={12}>
          <Flex direction="column" gap={4} style={{ flex: 1 }}>
            <Text fontWeight="medium">Answer proactively in all channels</Text>
            <Text color="tertiary">
              Configure whether the bot should proactively answer questions it thinks it can answer.
              Your slack bot will always respond to DM's and @ mentions.
            </Text>
          </Flex>
          <ToggleSwitch
            checked={proactivityEnabled}
            onChange={async (e) => {
              setProactivityEnabled(e.target.checked);
              await saveProactivityToggle(e.target.checked);
            }}
            disabled={saveStates.proactivityToggle}
          />
        </Flex>

        {/* Channel Settings */}
        <Flex direction="column" gap={16} width="100%">
          <Flex direction="column" gap={8}>
            <Text fontSize="md" fontWeight="medium">
              {proactivityEnabled
                ? 'Never answer proactively in specific channels'
                : 'Answer proactively in specific channels'}
            </Text>
            <div style={{ color: '#6c757d' }}>
              <Text fontSize="md">Enter channel names separated by commas (without # symbol)</Text>
            </div>
          </Flex>

          <Flex direction="row" gap={12} align="center" justify="space-between">
            <Input
              value={proactivityEnabled ? excludedChannels : allowedChannels}
              onChange={(e) =>
                proactivityEnabled
                  ? setExcludedChannels(e.target.value)
                  : setAllowedChannels(e.target.value)
              }
              placeholder={`e.g. ${proactivityEnabled ? 'general, announcements' : 'engineering, sales, marketing'}`}
              disabled={saveStates.channelSettings}
              size="lg"
              fullWidth
            />
            <Button onClick={saveChannelSettings} disabled={saveStates.channelSettings}>
              {saveStates.channelSettings ? 'Saving...' : 'Save'}
            </Button>
          </Flex>
        </Flex>

        {/* Confidence Threshold Slider */}
        <Flex direction="column" gap={16} width="100%">
          <Flex direction="column" gap={8}>
            <Text fontSize="md" fontWeight="medium">
              Answer confidence threshold
            </Text>
            <Text color="tertiary">
              Configure how confident the bot should be before answering proactively. We recommend
              requiring no more than 80% confidence. Proactive answers are often still useful, even
              with only moderate confidence.
            </Text>
          </Flex>

          <Flex direction="column" gap={12}>
            {/* avoiding onValueCommit because it doesn't seem to work as expected */}
            <Slider
              value={confidenceThreshold}
              onValueChange={handleConfidenceThresholdChange}
              min={20}
              max={100}
              step={5}
            />
            <Flex justify="center">
              <Text fontSize="sm" color="tertiary">
                <b>{confidenceThreshold}%</b> confidence threshold
              </Text>
            </Flex>
          </Flex>
        </Flex>
      </Flex>
    </Flex>
  );
});

ProactivitySettings.displayName = 'ProactivitySettings';

export { ProactivitySettings };
