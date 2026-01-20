import { useState, useEffect, type ChangeEvent } from 'react';
import type { FC } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Button,
  Flex,
  Text,
  TextArea,
  Box,
  Divider,
  Checkbox,
} from '@gathertown/gather-design-system';
import { BaseIntegration } from './BaseIntegration';
import { apiClient } from '../../api/client';
import type { Integration, GongWorkspace, GongWorkspaceSettings } from '../../types';
import { CopyButton } from '../shared/CopyButton';
import gongWebhookSetup from '../../assets/setup-screenshots/gong-webook-setup.png';
import gongWebhookTest from '../../assets/setup-screenshots/gong-webhook-test.png';
import gongWebhookSaveRule from '../../assets/setup-screenshots/gong-webhook-save-rule.png';
import { useGongStatus } from '../../connectors/gong/api';
import { getSupportContactText } from '../../constants';
import { useQueryClient } from '@tanstack/react-query';
import { connectorConfigQueryKey } from '../../api/config';

interface GongIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const GongIntegration: FC<GongIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const [isAwaitingVerification, setIsAwaitingVerification] = useState(false);
  const { data: gongStatus } = useGongStatus({
    refetchInterval: isAwaitingVerification ? 4000 : undefined,
  });

  const location = useLocation();
  const navigate = useNavigate();
  const [isConnecting, setIsConnecting] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [webhookUrl, setWebhookUrl] = useState<string>('');
  const [publicKey, setPublicKey] = useState<string>('');
  const [isSavingWebhook, setIsSavingWebhook] = useState(false);
  const [webhookSaveError, setWebhookSaveError] = useState<string | null>(null);
  const [webhookSaveSuccess, setWebhookSaveSuccess] = useState(false);

  // Workspace selection state
  const [workspaces, setWorkspaces] = useState<GongWorkspace[]>([]);
  const [isLoadingWorkspaces, setIsLoadingWorkspaces] = useState(false);
  const [selectedWorkspaces, setSelectedWorkspaces] = useState<string[] | 'none' | undefined>(
    undefined
  );
  const [isSavingWorkspaces, setIsSavingWorkspaces] = useState(false);
  const [workspaceSaveError, setWorkspaceSaveError] = useState<string | null>(null);

  const isConnected = Boolean(gongStatus?.configured);
  const isWebhookConfigured = Boolean(gongStatus?.webhook_public_key_present);
  const isWebhookVerified = Boolean(gongStatus?.webhook_verified);

  const isStepValid = (stepIndex: number): boolean => {
    // Step 0: Connect Gong - must be connected to proceed
    if (stepIndex === 0) {
      return isConnected;
    }

    // Step 1: Select Workspaces - always valid (selection is optional)
    if (stepIndex === 1) {
      return true;
    }

    // Step 2: Configure Webhook - optional, always allow next
    if (stepIndex === 2) {
      return true;
    }

    // Step 3: Status - always valid
    return true;
  };

  useEffect(() => {
    const fetchWebhookConfig = async () => {
      if (!isConnected) return;
      try {
        const response = await apiClient.get<{
          url: string;
          publicKeyPresent: boolean;
          publicKey: string | null;
        }>('/api/gong/webhook');
        setWebhookUrl(response.url);
        if (response.publicKey) {
          setPublicKey(response.publicKey);
        }
      } catch (error) {
        console.error('Error fetching Gong webhook config:', error);
      }
    };
    fetchWebhookConfig();
  }, [isConnected]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const success = params.get('success') === 'true';
    const error = params.get('error');

    if (success) {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });

      navigate('/integrations/gong', { replace: true });
      if (onInlineComplete) {
        onInlineComplete();
      }
      setIsConnecting(false);
      setFetchError(null);
    }

    if (error) {
      setIsConnecting(false);
      setFetchError(error);
      navigate('/integrations/gong', { replace: true });
    }
  }, [location.search, navigate, onInlineComplete, queryClient]);

  const handleConnect = async () => {
    setFetchError(null);
    setIsConnecting(true);
    try {
      const response = await apiClient.get<{ url: string }>('/api/gong/oauth/url');
      window.location.href = response.url;
    } catch (error) {
      console.error('Error starting Gong OAuth flow:', error);
      setFetchError('Failed to start Gong OAuth flow. Please try again.');
      setIsConnecting(false);
    }
  };

  const handleSaveWebhook = async () => {
    setWebhookSaveError(null);
    setWebhookSaveSuccess(false);
    setIsSavingWebhook(true);
    setIsAwaitingVerification(false);

    try {
      await apiClient.put('/api/gong/webhook', {
        publicKey: publicKey.trim(),
      });

      setWebhookSaveSuccess(true);
      setIsAwaitingVerification(true);
      setTimeout(() => setWebhookSaveSuccess(false), 3000);
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    } catch (error) {
      console.error('Error saving Gong webhook config:', error);
      setWebhookSaveError(
        'Failed to save webhook configuration. Please check your public key format.'
      );
    } finally {
      setIsSavingWebhook(false);
    }
  };

  useEffect(() => {
    if (isWebhookVerified) {
      setIsAwaitingVerification(false);
      setIsAwaitingVerification(false);
      setWebhookSaveSuccess(true);
      setTimeout(() => setWebhookSaveSuccess(false), 3000);
    }
  }, [isWebhookVerified]);

  useEffect(() => {
    return () => {
      setIsAwaitingVerification(false);
    };
  }, []);

  // Fetch workspaces when connected
  useEffect(() => {
    const fetchWorkspaces = async () => {
      if (!isConnected) return;
      setIsLoadingWorkspaces(true);
      try {
        const response = await apiClient.get<{ workspaces: GongWorkspace[] }>(
          '/api/gong/workspaces'
        );
        setWorkspaces(response.workspaces);

        // Auto-select if only one workspace
        if (response.workspaces.length === 1 && response.workspaces[0]) {
          setSelectedWorkspaces([response.workspaces[0].id]);
        }
      } catch (error) {
        console.error('Error fetching Gong workspaces:', error);
      } finally {
        setIsLoadingWorkspaces(false);
      }
    };
    fetchWorkspaces();
  }, [isConnected]);

  // Fetch current workspace settings
  useEffect(() => {
    const fetchWorkspaceSettings = async () => {
      if (!isConnected) return;
      try {
        const response = await apiClient.get<GongWorkspaceSettings>('/api/gong/workspace-settings');
        setSelectedWorkspaces(response.selectedWorkspaces);
      } catch (error) {
        console.error('Error fetching Gong workspace settings:', error);
      }
    };
    fetchWorkspaceSettings();
  }, [isConnected]);

  const handleSaveWorkspaces = async () => {
    setWorkspaceSaveError(null);
    setIsSavingWorkspaces(true);
    try {
      // Determine what to save based on selection
      let valueToSave: string[] | 'none' | undefined;
      if (Array.isArray(selectedWorkspaces)) {
        if (selectedWorkspaces.length === 0) {
          valueToSave = 'none';
        } else {
          // Always save explicit workspace IDs, even if all are selected
          // This ensures new workspaces added later aren't automatically included
          valueToSave = selectedWorkspaces;
        }
      } else if (selectedWorkspaces === 'none') {
        valueToSave = 'none';
      } else {
        // selectedWorkspaces === undefined (no selection made yet)
        // Treat as 'none' for backend storage
        valueToSave = undefined;
      }

      await apiClient.put('/api/gong/workspace-settings', {
        selectedWorkspaces: valueToSave,
      });
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    } catch (error) {
      console.error('Error saving Gong workspace settings:', error);
      setWorkspaceSaveError('Failed to save workspace settings. Please try again.');
    } finally {
      setIsSavingWorkspaces(false);
    }
  };

  const handleWorkspaceCheckboxChange = (workspaceId: string, checked: boolean) => {
    // Convert to array if needed
    let currentSelection: string[];
    if (selectedWorkspaces === 'none' || selectedWorkspaces === undefined) {
      currentSelection = [];
    } else {
      currentSelection = selectedWorkspaces;
    }

    // Update selection
    if (checked) {
      setSelectedWorkspaces([...currentSelection, workspaceId]);
    } else {
      setSelectedWorkspaces(currentSelection.filter((id) => id !== workspaceId));
    }
  };

  const handleSelectAll = () => {
    // Select all workspace IDs
    const allWorkspaceIds = workspaces.map((w) => w.id);
    setSelectedWorkspaces(allWorkspaceIds);
  };

  const handleSelectNone = () => {
    // Deselect all workspaces
    setSelectedWorkspaces([]);
  };

  const steps = [
    {
      title: 'Connect Gong',
      content: (
        <Flex direction="column" gap={16}>
          <Text>
            Connect your Gong account to sync call recordings and transcripts with Grapevine.
          </Text>

          {isConnected ? (
            <Flex direction="column" gap={12}>
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#d4edda',
                  borderRadius: '8px',
                  border: '1px solid #c3e6cb',
                }}
              >
                <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
                  ✓ Gong Account Connected
                </Text>
                <Text fontSize="sm" color="secondary">
                  Your Gong account is connected and call records will be ingested.
                </Text>
              </Flex>

              <Button onClick={handleConnect} kind="secondary" size="sm">
                Reconnect Gong
              </Button>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              <Text>
                Click the button below to connect your Gong account. You&apos;ll be redirected to
                Gong to authorize the connection.
              </Text>
              <Button
                onClick={handleConnect}
                kind="primary"
                loading={isConnecting}
                disabled={isConnecting}
              >
                {isConnecting ? 'Redirecting to Gong...' : 'Connect Gong Account'}
              </Button>
              <Text fontSize="sm" color="secondary">
                Make sure the user completing the authorization has the required Gong permissions to
                read calls and transcripts for your organization.
              </Text>

              {fetchError && (
                <Flex direction="column" gap={8}>
                  <Text color="dangerPrimary" fontWeight="semibold">
                    {fetchError}
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    {getSupportContactText()}
                  </Text>
                </Flex>
              )}
            </Flex>
          )}
        </Flex>
      ),
    },
    {
      title: 'Select Workspaces for Visibility',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md" fontWeight="semibold">
            Choose Workspace Visibility
          </Text>
          <Text fontSize="sm" color="secondary">
            Select which workspaces should have tenant-level visibility for public library calls.
            Unselected workspaces will still be ingested but all calls will be private-only (visible
            only to participants and users with appropriate permissions).
          </Text>

          {isLoadingWorkspaces ? (
            <Text fontSize="sm" color="secondary">
              Loading workspaces...
            </Text>
          ) : (
            <Flex direction="column" gap={12}>
              {workspaces.length > 0 && (
                <>
                  <Flex direction="row" gap={8} align="center">
                    <Button onClick={handleSelectAll} kind="secondary" size="sm">
                      Select All
                    </Button>
                    <Button onClick={handleSelectNone} kind="secondary" size="sm">
                      Deselect All
                    </Button>
                  </Flex>

                  <Flex
                    direction="column"
                    gap={8}
                    style={{
                      padding: '12px',
                      backgroundColor: '#f8f9fa',
                      borderRadius: '8px',
                      border: '1px solid #dee2e6',
                    }}
                  >
                    <Text fontSize="sm" fontWeight="semibold">
                      Workspaces
                    </Text>
                    {workspaces.map((workspace) => {
                      const isChecked =
                        Array.isArray(selectedWorkspaces) &&
                        selectedWorkspaces.includes(workspace.id);

                      return (
                        <Checkbox
                          key={workspace.id}
                          checked={isChecked}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            handleWorkspaceCheckboxChange(workspace.id, e.target.checked)
                          }
                          label={workspace.name}
                        />
                      );
                    })}
                  </Flex>
                </>
              )}

              <Button
                onClick={handleSaveWorkspaces}
                kind="primary"
                loading={isSavingWorkspaces}
                disabled={isSavingWorkspaces}
              >
                {isSavingWorkspaces ? 'Saving...' : 'Save Workspace Settings'}
              </Button>

              {workspaceSaveError && (
                <Text fontSize="sm" color="dangerPrimary" fontWeight="semibold">
                  {workspaceSaveError}
                </Text>
              )}
            </Flex>
          )}

          <Divider direction="horizontal" />

          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="semibold">
              How Visibility Works
            </Text>
            <Text fontSize="sm" color="secondary">
              <strong>Tenant-level visibility:</strong> When a call has tenant-level visibility, it
              can be used to answer questions asked in public Slack channels. This is typically
              public calls in library folders from selected workspaces.
            </Text>
            <Text fontSize="sm" color="secondary">
              <strong>Private visibility:</strong> When a call has private visibility, it can only
              be used to answer questions in direct messages (DMs), and only for users who have
              access to that call in Gong (participants, permission profiles, etc).
            </Text>
            <Text fontSize="sm" color="secondary">
              • <strong>Selected workspaces:</strong> Public library calls have tenant-level
              visibility
            </Text>
            <Text fontSize="sm" color="secondary">
              • <strong>Unselected workspaces:</strong> All calls have private-only visibility
            </Text>
            <Text fontSize="sm" color="secondary">
              Use "Select All" to make all public library calls tenant-level visible, or "Deselect
              All" to make all calls private-only.
            </Text>
          </Flex>
        </Flex>
      ),
    },
    {
      title: 'Configure Webhook (Optional)',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md" fontWeight="semibold">
            Enable Real-Time Sync
          </Text>
          <Text fontSize="sm" color="secondary">
            Configure Gong webhooks to receive real-time updates when calls are recorded.
          </Text>

          {isWebhookConfigured && isWebhookVerified && (
            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#d4edda',
                borderRadius: '8px',
                border: '1px solid #c3e6cb',
              }}
            >
              <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
                ✓ Webhook Verified
              </Text>
              <Text fontSize="sm" color="secondary">
                We received the test webhook from Gong. Real-time updates are enabled.
              </Text>
            </Flex>
          )}

          {isWebhookConfigured && !isWebhookVerified && (
            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#fff3cd',
                borderRadius: '8px',
                border: '1px solid #ffeaa7',
              }}
            >
              <Text fontSize="sm" color="warningPrimary" fontWeight="semibold">
                ⚠ Webhook Verification Pending
              </Text>
              <Text fontSize="sm" color="secondary">
                Click "TEST NOW" in Gong after saving the public key to finish verification.
              </Text>
            </Flex>
          )}

          {!isWebhookConfigured && (
            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                border: '1px solid #dee2e6',
              }}
            >
              <Text fontSize="sm" color="secondary" fontWeight="semibold">
                Optional: Enable Real-time Sync
              </Text>
              <Text fontSize="sm" color="secondary">
                Without webhook configuration, Grapevine will continue syncing Gong data on a
                schedule.
              </Text>
            </Flex>
          )}

          <Divider direction="horizontal" />

          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="semibold">
              Step 1: Copy Webhook URL
            </Text>
            <Text fontSize="sm" color="secondary">
              In Gong, go to Admin Center → Ecosystem → Automation Rules → Add rule → New rule →
              Action → Fire Webhook
            </Text>
            <Flex
              direction="row"
              align="center"
              gap={8}
              style={{
                padding: '8px 12px',
                backgroundColor: '#f5f5f5',
                borderRadius: '4px',
                border: '1px solid #e0e0e0',
              }}
            >
              <code
                style={{
                  flex: 1,
                  fontFamily: 'monospace',
                  fontSize: '12px',
                  wordBreak: 'break-all',
                }}
              >
                {webhookUrl || 'Loading...'}
              </code>
              {webhookUrl && <CopyButton textToCopy={webhookUrl} />}
            </Flex>
          </Flex>

          <Flex direction="column" gap={8}>
            <img
              src={gongWebhookSetup}
              alt="Gong webhook setup - showing URL input and JWT header selection"
              style={{
                maxWidth: '100%',
                borderRadius: '8px',
                border: '1px solid #dee2e6',
              }}
            />
          </Flex>

          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="semibold">
              Step 2: Select Authentication Method
            </Text>
            <Text fontSize="sm" color="secondary">
              In the Gong webhook configuration, select <strong>Signed JWT header</strong> as the
              authentication method.
            </Text>
          </Flex>

          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="semibold">
              Step 3: Copy Public Key from Gong
            </Text>
            <Text fontSize="sm" color="secondary">
              Click <strong>Show public key</strong> in Gong and copy the entire key.
            </Text>
          </Flex>

          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="semibold">
              Step 4: Paste Public Key Here
            </Text>
            <Box position="relative">
              <TextArea
                value={publicKey}
                onChange={(e) => setPublicKey(e.target.value)}
                placeholder={`MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...`}
                style={{
                  minHeight: '150px',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
            </Box>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Step 5: Save Rule
              </Text>
              <Text fontSize="sm" color="secondary">
                Name the rule and make sure "Rule status" is set to "Enabled"
              </Text>
              <img
                src={gongWebhookSaveRule}
                alt="Gong webhook save and activate rule"
                style={{
                  maxWidth: '100%',
                  borderRadius: '8px',
                  border: '1px solid #dee2e6',
                }}
              />
            </Flex>
            <Button
              kind="primary"
              onClick={handleSaveWebhook}
              disabled={!publicKey.trim() || isSavingWebhook}
              loading={isSavingWebhook}
            >
              {isSavingWebhook ? 'Saving...' : 'Save Webhook Configuration'}
            </Button>

            {webhookSaveSuccess && (
              <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
                ✓ Webhook configuration saved successfully!
              </Text>
            )}

            {webhookSaveError && (
              <Text fontSize="sm" color="dangerPrimary" fontWeight="semibold">
                {webhookSaveError}
              </Text>
            )}
          </Flex>

          {isAwaitingVerification && !isWebhookVerified && (
            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#fff3cd',
                borderRadius: '8px',
                border: '1px solid #ffeaa7',
              }}
            >
              <Flex direction="row" align="center" gap={8}>
                <Text fontSize="sm" color="warningPrimary" fontWeight="semibold">
                  Waiting for Gong test webhook...
                </Text>
              </Flex>
              <Text fontSize="sm" color="secondary">
                Click "TEST NOW" in Gong after saving the public key. We'll mark this step complete
                automatically when the test webhook arrives.
              </Text>
              <Flex direction="column" gap={8}>
                <img
                  src={gongWebhookTest}
                  alt="Gong webhook test button"
                  style={{
                    maxWidth: '100%',
                    borderRadius: '8px',
                    border: '1px solid #dee2e6',
                  }}
                />
              </Flex>
              <Text fontSize="xs" color="tertiary">
                You can continue configuring Gong in another tab while we listen for the test
                request.
              </Text>
            </Flex>
          )}

          <Text fontSize="xs" color="tertiary">
            Note: Webhook configuration is optional. Without it, Grapevine will sync data
            periodically.
          </Text>
        </Flex>
      ),
    },
    {
      title: 'Gong Integration Status',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md" fontWeight="semibold">
            Current Status
          </Text>

          <Flex
            direction="column"
            gap={8}
            style={{
              padding: '12px',
              backgroundColor: isConnected ? '#d4edda' : '#f8f9fa',
              borderRadius: '8px',
              border: `1px solid ${isConnected ? '#c3e6cb' : '#dee2e6'}`,
            }}
          >
            <Text
              fontSize="sm"
              color={isConnected ? 'successPrimary' : 'secondary'}
              fontWeight="semibold"
            >
              {isConnected ? '✓ Gong Account Connected' : '○ Gong Account Not Connected'}
            </Text>
            <Text fontSize="sm" color="secondary">
              {isConnected
                ? 'Your Gong account is connected and call records will be ingested.'
                : 'Complete the OAuth step to connect your Gong account and start ingestion.'}
            </Text>
          </Flex>

          <Flex
            direction="column"
            gap={8}
            style={{
              padding: '12px',
              backgroundColor:
                isWebhookConfigured && isWebhookVerified
                  ? '#d4edda'
                  : isWebhookConfigured
                    ? '#fff3cd'
                    : '#f8f9fa',
              borderRadius: '8px',
              border: `1px solid
                ${
                  isWebhookConfigured && isWebhookVerified
                    ? '#c3e6cb'
                    : isWebhookConfigured
                      ? '#ffeaa7'
                      : '#dee2e6'
                }`,
            }}
          >
            <Text
              fontSize="sm"
              color={
                isWebhookConfigured && isWebhookVerified
                  ? 'successPrimary'
                  : isWebhookConfigured
                    ? 'warningPrimary'
                    : 'secondary'
              }
              fontWeight="semibold"
            >
              {isWebhookConfigured && isWebhookVerified
                ? '✓ Webhook Verified'
                : isWebhookConfigured
                  ? '⚠ Webhook Configuration Pending Verification'
                  : '○ Webhook Not Configured'}
            </Text>
            <Text fontSize="sm" color="secondary">
              {isWebhookConfigured && isWebhookVerified
                ? 'Real-time updates are enabled. We will index calls as soon as Gong records them.'
                : isWebhookConfigured
                  ? 'Send a test webhook from Gong to finish verification. Until then we will fall back to periodic sync.'
                  : 'Webhook setup is optional but recommended for real-time syncing. Without it we continue scheduled backfills.'}
            </Text>
          </Flex>

          <Divider direction="horizontal" />

          <Button onClick={handleConnect} kind="secondary" size="sm" fullWidth>
            Reconnect Gong
          </Button>
        </Flex>
      ),
    },
  ];

  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  // Set initial step based on connection / webhook state
  useEffect(() => {
    if (steps.length === 0) {
      return;
    }

    if (!isConnected) {
      // Not connected -> always start at connect step
      setCurrentStepIndex(0);
      return;
    }

    if (isWebhookConfigured) {
      // Connected and webhook configured -> go to webhook configuration (now step 2)
      setCurrentStepIndex(2);
      return;
    }

    // Connected but no webhook -> show workspace selection step by default
    setCurrentStepIndex(1);
  }, [steps.length, isConnected, isWebhookConfigured]);

  // Handle step changes with auto-save for workspace selection
  const handleStepChange = async (newStepIndex: number) => {
    // Auto-save workspace settings when leaving step 1 (workspace selection)
    if (currentStepIndex === 1 && newStepIndex !== 1) {
      // Save workspace settings before changing steps
      await handleSaveWorkspaces();
    }
    setCurrentStepIndex(newStepIndex);
  };

  return (
    <BaseIntegration
      integration={integration}
      steps={steps}
      isModalOpen={isModalOpen}
      onModalOpenChange={onModalOpenChange}
      currentStepIndex={currentStepIndex}
      onStepChange={handleStepChange}
      isStepValid={isStepValid}
      onComplete={async () => {
        if (renderInline && onInlineComplete) {
          onInlineComplete();
        } else {
          onModalOpenChange(false);
        }
      }}
      renderStepContent={(step) => (typeof step.content === 'function' ? null : step.content)}
      renderInline={renderInline}
      hideNavigation={false}
      hideComplete={false}
      isConnected={isConnected}
      pendingVerification={isAwaitingVerification && !isWebhookVerified}
    />
  );
};
