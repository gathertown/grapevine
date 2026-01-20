import { useState, useEffect, FC, memo, ChangeEvent } from 'react';
import {
  Flex,
  Text,
  Button,
  Icon,
  Modal,
  Select,
  type SelectOption,
  IconButton,
  Divider,
  ToggleSwitch,
} from '@gathertown/gather-design-system';
import { apiClient } from '../api/client';
import { SectionHeader } from './shared/SectionHeader';
import { SectionContainer } from './shared/SectionContainer';
import { useAllConfig } from '../api/config';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { connectorConfigQueryKey } from '../api/config';
import { useLinearTeams, type LinearTeam } from '../api/linear';
import { useTrackEvent } from '../hooks/useTrackEvent';
import existingTicketFoundImg from '../assets/images/triage/existing-ticket-found.jpg';

interface MappingRow {
  id: string;
  channelId: string;
  teamId: string;
}

interface LinearTeamMapping {
  linearTeam: LinearTeam;
  channels: string[];
}

interface SlackChannel {
  id: string;
  name: string;
}

const TriageBotPage: FC = memo(() => {
  const { data: configData } = useAllConfig();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { trackEvent } = useTrackEvent();
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [showDisconnectModal, setShowDisconnectModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Team mappings state
  const [teams, setTeams] = useState<LinearTeam[]>([]);
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([]);
  const [mappings, setMappings] = useState<MappingRow[]>([]);
  const [originalMappings, setOriginalMappings] = useState<MappingRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showSavedMessage, setShowSavedMessage] = useState(false);

  // Proactive mode state
  const [proactiveMode, setProactiveMode] = useState(true);
  const [proactiveModeLoading, setProactiveModeLoading] = useState(false);
  const [proactiveModeSaving, setProactiveModeSaving] = useState(false);

  const isSlackConnected = !!configData?.SLACK_BOT_TOKEN && !!configData?.SLACK_SIGNING_SECRET;
  const isLinearConnected = !!configData?.LINEAR_ACCESS_TOKEN || !!configData?.LINEAR_API_KEY;
  const isLinearWriteConnected = configData?.TRIAGE_BOT_LINEAR_CONNECTED === 'true';

  // Handle OAuth callback redirect
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const errorParam = params.get('error') === 'true';

    if (success) {
      trackEvent('triage_bot_enabled', {});
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
      setError(null);
      navigate('/apps/triage', { replace: true });
    }

    if (errorParam) {
      setError('Failed to connect Linear. Please try again.');
      navigate('/apps/triage', { replace: true });
    }
  }, [location.search, navigate, queryClient, trackEvent]);

  // Load Linear teams using backend endpoint
  const { data: fetchedTeams = [], error: teamsError, isLoading: teamsLoading } = useLinearTeams();

  // Load teams and mappings (helper function defined later)
  const loadTeamsAndMappings = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch channels from Slack and mappings in parallel
      const [slackChannelsResponse, mappingsResponse] = await Promise.all([
        apiClient.get<{ channels: SlackChannel[] }>('/api/slack/channels'),
        apiClient.get<{ mappings: LinearTeamMapping[] }>(
          '/api/exponent/admin/linear-team-mappings'
        ),
      ]);

      setTeams(fetchedTeams);
      setSlackChannels(slackChannelsResponse.channels);

      // Explode mappings: 1 team with many channels → many rows (1 per channel)
      const rows: MappingRow[] = [];
      mappingsResponse.mappings.forEach((mapping) => {
        mapping.channels.forEach((channelId) => {
          rows.push({
            id: `row-${Date.now()}-${Math.random()}`,
            teamId: mapping.linearTeam.id,
            channelId,
          });
        });
      });

      setMappings(rows);
      setOriginalMappings(JSON.parse(JSON.stringify(rows))); // Deep copy
    } catch (err) {
      console.error('Failed to load teams and mappings:', err);
      setError('Failed to load teams and mappings. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Load teams and mappings when connected with write access and teams are loaded
  useEffect(() => {
    if (isLinearWriteConnected && fetchedTeams.length > 0 && !teamsLoading) {
      loadTeamsAndMappings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLinearWriteConnected, fetchedTeams.length, teamsLoading]);

  // Handle teams error
  useEffect(() => {
    if (teamsError) {
      setError('Failed to load Linear teams. Please try again.');
    }
  }, [teamsError]);

  // Load proactive mode setting when connected with write access
  useEffect(() => {
    const loadProactiveMode = async () => {
      if (!isLinearWriteConnected) return;

      try {
        setProactiveModeLoading(true);
        const response = await apiClient.get<{ enabled: boolean }>(
          '/api/exponent/admin/triage-proactive-mode'
        );
        setProactiveMode(response.enabled);
      } catch (err) {
        console.error('Failed to load proactive mode setting:', err);
        // Keep default value (true) on error
      } finally {
        setProactiveModeLoading(false);
      }
    };

    loadProactiveMode();
  }, [isLinearWriteConnected]);

  // Track page view when config loads
  useEffect(() => {
    if (configData) {
      trackEvent('triage_bot_page_viewed', {
        has_linear_write_access: isLinearWriteConnected,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configData]); // Only track once when config loads

  // Show loading state while config is loading
  if (!configData) {
    return (
      <Flex width="100%" direction="column" gap={32}>
        <Text color="tertiary">Loading...</Text>
      </Flex>
    );
  }

  const handleDisconnectClick = () => {
    setShowDisconnectModal(true);
  };

  const handleConfirmDisconnect = async () => {
    setShowDisconnectModal(false);
    setIsDisconnecting(true);
    try {
      await apiClient.delete('/api/linear/disconnect');
      trackEvent('triage_bot_disconnected', {});
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    } catch (err) {
      console.error('Failed to disconnect Linear:', err);
      setError('Failed to disconnect Linear. Please try again.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  // Add a new mapping row
  const handleAddRow = () => {
    const newRow: MappingRow = {
      id: `row-${Date.now()}-${Math.random()}`,
      channelId: '',
      teamId: '',
    };
    setMappings([...mappings, newRow]);
  };

  // Delete a mapping row
  const handleDeleteRow = (rowId: string) => {
    setMappings(mappings.filter((row) => row.id !== rowId));
  };

  // Update channel ID for a row
  const handleChannelChange = (rowId: string, value: string) => {
    setMappings(mappings.map((row) => (row.id === rowId ? { ...row, channelId: value } : row)));
  };

  // Update team selection for a row
  const handleTeamChange = (rowId: string, value: string) => {
    setMappings(mappings.map((row) => (row.id === rowId ? { ...row, teamId: value } : row)));
  };

  // Save mappings
  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      // Consolidate rows: many rows → teams with channel arrays
      const consolidatedMappings: Record<string, { linearTeam: LinearTeam; channels: string[] }> =
        {};

      mappings.forEach((row) => {
        if (row.teamId && row.channelId) {
          const team = teams.find((t) => t.id === row.teamId);
          if (team) {
            if (!consolidatedMappings[row.teamId]) {
              consolidatedMappings[row.teamId] = {
                linearTeam: team,
                channels: [],
              };
            }
            if (!consolidatedMappings[row.teamId]?.channels.includes(row.channelId)) {
              consolidatedMappings[row.teamId]?.channels.push(row.channelId);
            }
          }
        }
      });

      const mappingsArray = Object.values(consolidatedMappings);

      await apiClient.post('/api/exponent/admin/linear-team-mappings', {
        mappings: mappingsArray,
      });

      trackEvent('triage_bot_mappings_saved', {
        mapping_count: mappings.length,
      });

      setOriginalMappings(JSON.parse(JSON.stringify(mappings))); // Update baseline
      setShowSavedMessage(true);
      setTimeout(() => setShowSavedMessage(false), 3000);
    } catch (err) {
      console.error('Failed to save mappings:', err);
      setError('Failed to save mappings. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Handle proactive mode toggle
  const handleProactiveModeToggle = async (e: ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    try {
      setProactiveModeSaving(true);
      setProactiveMode(checked);

      await apiClient.post('/api/exponent/admin/triage-proactive-mode', {
        enabled: checked,
      });

      trackEvent('triage_bot_proactive_mode_toggled', {
        enabled: checked,
      });
    } catch (err) {
      console.error('Failed to save proactive mode setting:', err);
      setError('Failed to save proactive mode setting. Please try again.');
      // Revert on error
      setProactiveMode(!checked);
    } finally {
      setProactiveModeSaving(false);
    }
  };

  // Check if mappings have changed (dirty state)
  const isDirty =
    JSON.stringify(mappings.map((m) => ({ channelId: m.channelId, teamId: m.teamId }))) !==
    JSON.stringify(originalMappings.map((m) => ({ channelId: m.channelId, teamId: m.teamId })));

  // Check if any row is invalid
  const hasInvalidRows = mappings.some((row) => !row.channelId.trim() || !row.teamId);

  // Convert teams to SelectOption format
  const teamOptions: SelectOption[] = teams
    .map((team) => ({
      label: team.name,
      value: team.id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));

  // Convert Slack channels to SelectOption format
  const channelOptions: SelectOption[] = slackChannels
    .map((channel) => ({
      label: `#${channel.name}`,
      value: channel.id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));

  return (
    <Flex width="100%" direction="column" gap={32}>
      <Flex direction="column">
        <SectionHeader title="Triage Bot" />
        <SectionContainer>
          <Flex direction="column" gap={16}>
            {/* How does it work section with images */}

            <img
              src={existingTicketFoundImg}
              alt="Existing ticket found"
              style={{
                width: '400px',
                objectFit: 'cover',
                borderRadius: '8px',
              }}
            />

            <Flex direction="column" gap={8} mb={8}>
              <Text fontSize="md" fontWeight="semibold">
                How does it work?
              </Text>
              <Text fontSize="sm" color="tertiary">
                Once you enable it in a Slack channel, all new top-level messages will be
                automatically triaged and synced to Linear, updating an existing ticket or creating
                a new one as needed.
              </Text>
            </Flex>

            <Divider direction="horizontal" />

            {/* Prerequisites Check */}
            {(!isSlackConnected || !isLinearConnected || !isLinearWriteConnected) && (
              <Flex direction="column" gap={8}>
                <Flex mb={8}>
                  <Text fontSize="md" fontWeight="semibold">
                    Set up
                  </Text>
                </Flex>

                {/* Slack Status */}
                <Flex
                  direction="row"
                  align="center"
                  justify="space-between"
                  style={{
                    height: '52px',
                    padding: '12px',
                    backgroundColor: isSlackConnected ? '#EEFFF3' : '#FFF4ED',
                    borderRadius: '8px',
                    border: isSlackConnected ? '1px solid #B2FFCC' : '1px solid #FFE6D5',
                  }}
                >
                  <Flex direction="row" align="center" gap={8}>
                    <Icon
                      name={isSlackConnected ? 'checkCircle' : 'exclamationCircle'}
                      size="md"
                      color={isSlackConnected ? 'successPrimary' : 'warningPrimary'}
                    />
                    <Text fontSize="sm" fontWeight="semibold">
                      Ask Grapevine
                    </Text>
                  </Flex>
                  {!isSlackConnected && (
                    <Button
                      onClick={() => navigate('/apps/ask-grapevine')}
                      kind="secondary"
                      size="sm"
                    >
                      Connect Ask Grapevine
                    </Button>
                  )}
                </Flex>

                {/* Linear Status */}
                <Flex
                  direction="row"
                  align="center"
                  justify="space-between"
                  style={{
                    height: '52px',
                    padding: '12px',
                    backgroundColor: isLinearConnected ? '#EEFFF3' : '#FFF4ED',
                    borderRadius: '8px',
                    border: isLinearConnected ? '1px solid #B2FFCC' : '1px solid #FFE6D5',
                  }}
                >
                  <Flex direction="row" align="center" gap={8}>
                    <Icon
                      name={isLinearConnected ? 'checkCircle' : 'exclamationCircle'}
                      size="md"
                      color={isLinearConnected ? 'successPrimary' : 'warningPrimary'}
                    />
                    <Text fontSize="sm" fontWeight="semibold">
                      Linear Integration
                    </Text>
                  </Flex>
                  {!isLinearConnected && (
                    <Button
                      onClick={async () => {
                        const response = await apiClient.get<{ url: string }>(
                          '/api/linear/install?write=true&redirect=/apps/triage'
                        );
                        window.location.href = response.url;
                      }}
                      kind="primary"
                      size="sm"
                    >
                      Connect Linear
                    </Button>
                  )}
                </Flex>

                {/* Linear Write Access Status - Only show when Linear is connected */}
                {isLinearConnected && (
                  <Flex
                    direction="row"
                    align="center"
                    justify="space-between"
                    style={{
                      height: '52px',
                      padding: '12px',
                      backgroundColor: isLinearWriteConnected ? '#EEFFF3' : '#FFF4ED',
                      borderRadius: '8px',
                      border: isLinearWriteConnected ? '1px solid #B2FFCC' : '1px solid #FFE6D5',
                    }}
                  >
                    <Flex direction="row" align="center" gap={8}>
                      <Icon
                        name={isLinearWriteConnected ? 'checkCircle' : 'exclamationCircle'}
                        size="md"
                        color={isLinearWriteConnected ? 'successPrimary' : 'warningPrimary'}
                      />
                      <Text fontSize="sm" fontWeight="semibold">
                        Linear Write Access
                      </Text>
                    </Flex>
                    {!isLinearWriteConnected && (
                      <Button
                        onClick={async () => {
                          const response = await apiClient.get<{ url: string }>(
                            '/api/linear/install?write=true&redirect=/apps/triage'
                          );
                          window.location.href = response.url;
                        }}
                        kind="primary"
                        size="sm"
                      >
                        Enable Write Access
                      </Button>
                    )}
                  </Flex>
                )}
              </Flex>
            )}

            {/* Success message - Only show when all prerequisites are met */}
            {isLinearConnected && isSlackConnected && isLinearWriteConnected && (
              <Flex direction="column" gap={12}>
                <Flex
                  direction="row"
                  align="center"
                  justify="space-between"
                  style={{
                    padding: '12px',
                    backgroundColor: '#EEFFF3',
                    borderRadius: '8px',
                    border: '1px solid #B2FFCC',
                  }}
                  mt={8}
                >
                  <Flex direction="row" align="center" gap={8}>
                    <Icon name="checkCircle" size="md" color="successPrimary" />
                    <Text fontSize="sm" fontWeight="medium">
                      Triage Bot Enabled
                    </Text>
                  </Flex>
                  <Button
                    onClick={handleDisconnectClick}
                    kind="dangerSecondary"
                    size="sm"
                    loading={isDisconnecting}
                    disabled={isDisconnecting}
                  >
                    Disconnect
                  </Button>
                </Flex>

                {/* Proactive Mode Toggle */}
                <Flex direction="column" gap={16} mt={12}>
                  <Divider direction="horizontal" />
                  <Flex direction="column" gap={12}>
                    <Flex direction="row" justify="space-between" align="center" gap={24}>
                      <Flex direction="column" gap={8} style={{ flex: 1 }}>
                        <Text fontSize="md" fontWeight="semibold">
                          Proactive Mode
                        </Text>
                        <Text fontSize="sm" color="tertiary">
                          When enabled, the triage bot automatically creates or updates Linear
                          tickets as soon as it analyzes a message. When disabled, it shows you the
                          analysis and waits for you to click a button to confirm the action.
                        </Text>
                      </Flex>
                      <ToggleSwitch
                        checked={proactiveMode}
                        onChange={handleProactiveModeToggle}
                        disabled={proactiveModeLoading || proactiveModeSaving}
                      />
                    </Flex>
                  </Flex>
                </Flex>

                {/* Team Mappings Section */}
                <Flex direction="column" gap={16} mt={24}>
                  <Flex direction="column" gap={8}>
                    <Text fontSize="md" fontWeight="semibold">
                      Where should the Triage Bot create Linear issues?
                    </Text>
                    <Text fontSize="sm" color="tertiary">
                      Choose which Slack channels the bot should watch. When someone posts a bug
                      report in one of these channels, the bot will analyze it and create or update
                      a Linear issue for the team you choose.
                    </Text>
                    <Flex align="center" gap={2} mt={4}>
                      <Icon name="infoCircle" size="xs" color="tertiary" />
                      <Text fontSize="xs" color="tertiary">
                        Don't see your Slack channel? Make sure the Grapevine bot is invited to it.
                      </Text>
                    </Flex>
                  </Flex>

                  {loading ? (
                    <Text color="tertiary">
                      Loading Linear teams, Slack channels, and mappings...
                    </Text>
                  ) : error && teams.length === 0 ? (
                    <Flex direction="column" gap={12}>
                      <Text fontSize="sm" color="dangerPrimary">
                        {error}
                      </Text>
                      <Button onClick={loadTeamsAndMappings} size="sm">
                        Retry
                      </Button>
                    </Flex>
                  ) : (
                    <Flex direction="column" gap={16}>
                      {mappings.length === 0 ? (
                        <Flex direction="column" gap={12}>
                          <Flex
                            direction="column"
                            align="center"
                            justify="center"
                            gap={12}
                            style={{
                              padding: '48px 24px',
                              border: '2px dashed #ddd',
                              borderRadius: '8px',
                            }}
                          >
                            <Icon name="link" size="lg" color="tertiary" />
                            <Text fontWeight="semibold" textAlign="center">
                              No channels added yet
                            </Text>
                            <Text fontSize="sm" color="secondary" textAlign="center">
                              Add a Slack channel to tell the triage bot where to send new issues.
                            </Text>
                            <Button onClick={handleAddRow} size="sm" leadingIcon="plus">
                              Add channel
                            </Button>
                          </Flex>
                          {(isDirty || showSavedMessage) && (
                            <Flex direction="row" gap={8} justify="flex-end" align="center">
                              {showSavedMessage && (
                                <Text fontSize="sm" color="successPrimary">
                                  Saved!
                                </Text>
                              )}
                              {isDirty && (
                                <Button
                                  onClick={handleSave}
                                  kind="primary"
                                  size="sm"
                                  loading={saving}
                                  disabled={saving}
                                >
                                  {saving ? 'Saving...' : 'Save settings'}
                                </Button>
                              )}
                            </Flex>
                          )}
                        </Flex>
                      ) : (
                        <Flex direction="column" gap={8}>
                          {mappings.map((row) => (
                            <Flex key={row.id} direction="row" gap={8} align="center">
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <Select
                                  value={row.channelId}
                                  onChange={(value: string) => handleChannelChange(row.id, value)}
                                  options={channelOptions}
                                  placeholder="Select a channel"
                                  renderOption={(option: SelectOption) => (
                                    <span
                                      style={{
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                        display: 'block',
                                      }}
                                    >
                                      {option.label}
                                    </span>
                                  )}
                                />
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <Select
                                  value={row.teamId}
                                  onChange={(value: string) => handleTeamChange(row.id, value)}
                                  options={teamOptions}
                                  placeholder="Select a team"
                                  renderOption={(option: SelectOption) => (
                                    <span
                                      style={{
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                        display: 'block',
                                      }}
                                    >
                                      {option.label}
                                    </span>
                                  )}
                                />
                              </div>
                              <IconButton
                                onClick={() => handleDeleteRow(row.id)}
                                kind="transparent"
                                size="sm"
                                icon="trash"
                                aria-label="Delete mapping"
                              />
                            </Flex>
                          ))}

                          <Flex direction="row" gap={8} justify="space-between" align="center">
                            <Button onClick={handleAddRow} size="sm" leadingIcon="plus">
                              Add channel
                            </Button>

                            <Flex direction="row" gap={8} align="center">
                              {showSavedMessage && (
                                <Text fontSize="sm" color="successPrimary">
                                  Saved!
                                </Text>
                              )}
                              {isDirty && (
                                <Button
                                  onClick={handleSave}
                                  kind="primary"
                                  size="sm"
                                  loading={saving}
                                  disabled={saving || hasInvalidRows}
                                >
                                  {saving ? 'Saving...' : 'Save settings'}
                                </Button>
                              )}
                            </Flex>
                          </Flex>
                        </Flex>
                      )}
                    </Flex>
                  )}
                </Flex>
              </Flex>
            )}
          </Flex>
        </SectionContainer>
      </Flex>

      {/* Disconnect Confirmation Modal */}
      <Modal open={showDisconnectModal} onOpenChange={setShowDisconnectModal}>
        <Modal.Content style={{ width: '500px' }} variant="auto">
          <Modal.Header title="Disconnect Linear?" />
          <Modal.Body>
            <Flex direction="column" gap={16}>
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#fff3cd',
                  borderRadius: '8px',
                  border: '1px solid #ffc107',
                }}
              >
                <Flex direction="row" align="center" gap={8}>
                  <Icon name="exclamationTriangle" size="md" color="warningPrimary" />
                  <Text fontSize="sm" fontWeight="semibold">
                    This will disconnect both the triage bot AND your regular Linear integration
                  </Text>
                </Flex>
              </Flex>

              <Flex direction="column" gap={8}>
                <Text fontSize="sm" color="secondary">
                  Disconnecting will remove Linear OAuth access for:
                </Text>
                <Flex direction="column" gap={4} style={{ paddingLeft: '16px' }}>
                  <Text fontSize="sm" color="secondary">
                    • Triage bot (creating/updating issues from Slack)
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    • Regular Linear integration (data indexing)
                  </Text>
                </Flex>
              </Flex>

              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#e7f3ff',
                  borderRadius: '8px',
                  border: '1px solid #b3d9ff',
                }}
              >
                <Text fontSize="sm" color="secondary">
                  <strong>Note:</strong> Your Linear data will NOT be deleted. To delete Linear
                  data, go to General → Delete Data.
                </Text>
              </Flex>

              <Flex direction="row" gap={8} justify="flex-end">
                <Button
                  onClick={() => setShowDisconnectModal(false)}
                  kind="secondary"
                  disabled={isDisconnecting}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleConfirmDisconnect}
                  kind="danger"
                  loading={isDisconnecting}
                  disabled={isDisconnecting}
                >
                  Disconnect Linear
                </Button>
              </Flex>
            </Flex>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </Flex>
  );
});

TriageBotPage.displayName = 'TriageBotPage';

export { TriageBotPage };
