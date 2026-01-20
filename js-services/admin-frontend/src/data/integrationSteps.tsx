import { Flex, Text, Input, Badge } from '@gathertown/gather-design-system';
import type { ConnectionStep } from '../types';
import { SlackDropzone } from '../components/SlackDropzone';
import { SlackExportsList } from '../components/SlackExportsList';
import { LinkRequiredStep } from '../components/shared/LinkRequiredStep';
import { UIHighlight } from '../components/shared/UIHighlight';
import { CopyButton } from '../components/shared/CopyButton';
import styles from './IntegrationSteps.module.css';

// Notion screenshots
import notionCreateIntegration from '../assets/setup-screenshots/notion-create-integration.png';
import notionTokenConfig from '../assets/setup-screenshots/notion-token-config.png';
import notionCapabilitiesReadonly from '../assets/setup-screenshots/notion-capabilities-readonly.png';
import notionAccessSharing from '../assets/setup-screenshots/notion-access-sharing.png';
import notionAccessTab from '../assets/setup-screenshots/notion-access-tab.png';
import notionWebhookConfig from '../assets/setup-screenshots/notion-webhook-config.png';
import notionWebhooksTab from '../assets/setup-screenshots/notion-webhooks-tab.png';
import notionWebhookVerification from '../assets/setup-screenshots/notion-webhook-verification.png';
import notionVerificationUI from '../assets/setup-screenshots/notion_verification_ui.png';

// GitHub screenshots
import githubTokenConfig from '../assets/setup-screenshots/github-token-config.png';
import githubRepoAccess from '../assets/setup-screenshots/github-repo-access.png';
import githubPermissions from '../assets/setup-screenshots/github-permissions.png';
import githubTokenGenerated from '../assets/setup-screenshots/github-token-generated.png';
import githubOrgSettings from '../assets/setup-screenshots/github-org-settings.png';
import githubWebhooksPage from '../assets/setup-screenshots/github-webhooks-page.png';
import githubWebhookConfig from '../assets/setup-screenshots/github-webhook-config.png';

// Google Drive screenshots
import googleAddClient from '../assets/setup-screenshots/google-add-client.png';
import googleAddClientId from '../assets/setup-screenshots/google-add-client-id.png';

// Linear screenshots
import linearApiKeyCreation from '../assets/setup-screenshots/linear-api-key-creation.png';
import linearApiKeyGenerated from '../assets/setup-screenshots/linear-api-key-generated.png';
import linearWebhookCreation from '../assets/setup-screenshots/linear-webhook-creation.png';
import linearWebhookConfig from '../assets/setup-screenshots/linear-webhook-config.png';

// Salesforce screenshots
import salesforceCdc from '../assets/setup-screenshots/salesforce_cdc.png';

import { Link } from 'react-router-dom';

export const integrationSteps: Record<string, ConnectionStep[]> = {
  notion: [
    {
      title: 'Create Integration',
      content: ({ linkClickStates: _linkClickStates, onLinkClick }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="md" fontWeight="semibold">
            Create Integration
          </Text>
          <LinkRequiredStep
            descriptionBefore="Visit"
            linkText="Notion integrations page"
            descriptionAfter="to create a new integration with a descriptive name (e.g., 'Grapevine Ingest')."
            linkUrl="https://www.notion.so/profile/integrations/form/new-integration"
            onLinkClick={() => onLinkClick?.('createIntegration')}
            size="md"
            additionalContent={
              <img
                src={notionCreateIntegration}
                alt="New integration form with name field"
                style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
              />
            }
          />
        </Flex>
      ),
      requiresInput: true,
      requiresLinkClick: true,
      validateInput: (_value, _inputValue, _hasError, linkClickStates) => {
        return Boolean(linkClickStates?.createIntegration);
      },
    },
    {
      title: 'Copy Integration Token',
      content: ({ inputValue, onInputChange, hasError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Copy Integration Token</span>
          </Text>
          <Text fontSize="md">
            Under the <UIHighlight>Configuration</UIHighlight> tab, copy the "Internal Integration
            Token" and paste it below
          </Text>
          <img
            src={notionTokenConfig}
            alt="Configuration tab showing Internal Integration Token"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Input
            placeholder="ntn_..."
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            type="password"
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
            error={
              hasError && inputValue
                ? 'Please enter a valid integration token starting with "ntn_"'
                : undefined
            }
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        if (!value.startsWith('ntn_')) return false;
        if (value.length < 20) return false; // Basic length check for token validity
        return true;
      },
    },
    {
      title: 'Set Capabilities',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Set Capabilities</span>
          </Text>
          <Text fontSize="md">
            Ensure your integration has <strong>read-only</strong> capabilities for security, like
            below:
          </Text>
          <img
            src={notionCapabilitiesReadonly}
            alt="Integration capabilities settings with read-only selected"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Grant Access',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Grant Access</span>
          </Text>
          <Text fontSize="md">
            Navigate to the <UIHighlight>Access</UIHighlight> tab:
          </Text>
          <img
            src={notionAccessTab}
            alt="Access tab interface in Notion integration settings"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Text fontSize="md">Then, choose the team spaces and pages you want to index:</Text>
          <img
            src={notionAccessSharing}
            alt="Access tab showing workspace sharing options"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Configure Webhook',
      content: ({ webhookUrls, onCopyWebhookUrl: _onCopyWebhookUrl, nonceError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Configure Webhook</span>
          </Text>
          <Text fontSize="md">
            Navigate to the <UIHighlight>Webhooks</UIHighlight> tab:
          </Text>
          <img
            src={notionWebhooksTab}
            alt="Notion webhooks tab"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Text fontSize="md">Then, create a subscription with the following webhook URL:</Text>
          {nonceError && (
            <div
              style={{
                backgroundColor: '#f8d7da',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #f5c6cb',
              }}
            >
              <Text fontSize="sm">
                <strong>Error:</strong> {nonceError}
              </Text>
            </div>
          )}
          <div
            style={{
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: 8,
              border: '1px solid #e0e0e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
            }}
          >
            <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
              {webhookUrls?.NOTION || 'Loading...'}
            </code>
            <CopyButton textToCopy={webhookUrls?.NOTION || ''} disabled={!webhookUrls?.NOTION} />
          </div>
          <img
            src={notionWebhookConfig}
            alt="Webhook configuration with URL field"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Verify Webhook',
      content: ({ webhookSecret, onCopySecret }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Verify Webhook</span>
          </Text>
          <Text fontSize="md">
            Click on the "Verify" button in Notion UI. After that, come back to this page.
          </Text>
          <img
            src={notionWebhookVerification}
            alt="Webhook verification process with token display"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          {webhookSecret ? (
            <div
              style={{
                backgroundColor: '#d4edda',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #c3e6cb',
              }}
            >
              <Text fontSize="sm">
                <strong>✓ Verification Token Received:</strong>
              </Text>
              <div
                style={{
                  backgroundColor: 'white',
                  padding: '8px',
                  borderRadius: 4,
                  border: '1px solid #ddd',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  marginTop: '8px',
                }}
              >
                <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                  {webhookSecret}
                </code>
                <CopyButton
                  textToCopy={webhookSecret || ''}
                  disabled={!webhookSecret}
                  onCopy={onCopySecret}
                />
              </div>
              <Text fontSize="sm">Make sure to paste this secret back in Notion!</Text>
            </div>
          ) : (
            <div
              style={{
                backgroundColor: '#fff3cd',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #ffeaa7',
              }}
            >
              <Text fontSize="sm">
                <strong>Waiting for verification token...</strong>
              </Text>
              <Text fontSize="sm">
                We're listening for the webhook verification token from Notion. Click "Verify" in
                the Notion UI to send it to Grapevine.
              </Text>
            </div>
          )}
          <img
            src={notionVerificationUI}
            alt="Webhook verification UI with secret input display"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: () => false, // This will be overridden by checking webhook secret existence
    },
  ],
  slack: [
    {
      title: '',
      content: ({
        slackBotConfigured,
        slackUploadStatus,
        resetSlackUpload,
        elapsedTime,
        slackExports,
        onFileChange,
        configData,
      }) => {
        // Format elapsed time
        const formatElapsedTime = (seconds: number): string => {
          const hours = Math.floor(seconds / 3600);
          const minutes = Math.floor((seconds % 3600) / 60);
          const secs = seconds % 60;

          if (hours > 0) {
            return `${hours}h ${minutes}m`;
          } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
          } else {
            return `${secs}s`;
          }
        };

        // Get team domain for export URL
        const teamDomain = configData?.SLACK_TEAM_DOMAIN || null;
        const exportUrl = teamDomain
          ? `https://${teamDomain}.slack.com/services/export`
          : 'https://slack.com/help/articles/201658943-Export-your-workspace-data';

        return (
          <Flex direction="column" gap={16}>
            <Text fontSize="md">
              {teamDomain ? (
                <>
                  Export your Slack workspace data and upload the .zip file to give Grapevine access
                  to historical context.
                </>
              ) : (
                <>
                  Upload a .zip file containing your Slack workspace export to catch up on
                  historical context.
                </>
              )}
            </Text>
            <Flex direction="column" gap={8}>
              {teamDomain ? (
                <>
                  <Text fontSize="sm" color="secondary">
                    1. Visit your{' '}
                    <a
                      href={exportUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#007bff', textDecoration: 'underline' }}
                    >
                      Slack export page
                    </a>
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    2. Start both a "Public Channels" export and a "Direct Messages" export
                  </Text>
                  <Text fontSize="sm" color="secondary">
                    3. Download the .zip files when ready and upload them below
                  </Text>
                </>
              ) : (
                <Text fontSize="sm" color="secondary">
                  <a
                    href={exportUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#007bff' }}
                  >
                    Learn how to export your Slack data
                  </a>
                </Text>
              )}
            </Flex>

            {!slackBotConfigured ? (
              <Badge
                color="warning"
                // @ts-expect-error - Badge text prop expects string but we need JSX with Link
                text={
                  <>
                    You must complete the{' '}
                    <Link to="/slackbot" style={{ color: '#007bff', textDecoration: 'underline' }}>
                      Create Your Slack Bot
                    </Link>{' '}
                    step before uploading your export
                  </>
                }
              />
            ) : (
              <>
                {/* File Upload States */}
                {slackUploadStatus &&
                  !slackUploadStatus?.uploading &&
                  !slackUploadStatus?.completed && (
                    <SlackDropzone
                      onFileChange={onFileChange}
                      disabled={!slackBotConfigured}
                      hasError={!!slackUploadStatus?.error}
                      errorMessage={
                        slackUploadStatus?.error ? `❌ ${slackUploadStatus.error}` : null
                      }
                    />
                  )}

                {/* Uploading State */}
                {slackUploadStatus?.uploading && (
                  <div
                    style={{
                      backgroundColor: '#e3f2fd',
                      padding: '16px',
                      borderRadius: '8px',
                      border: '1px solid #2196f3',
                    }}
                  >
                    <Flex direction="column" gap={12}>
                      <Flex direction="row" align="center" gap={12}>
                        <div className={styles.uploadingSpinner} />
                        <Text fontSize="md">
                          Uploading export... {slackUploadStatus?.progress}%
                        </Text>
                      </Flex>

                      <div style={{ color: '#666' }}>
                        <Text fontSize="sm">{slackUploadStatus?.filename}</Text>
                      </div>

                      <div
                        style={{
                          width: '100%',
                          height: '8px',
                          backgroundColor: '#e0e0e0',
                          borderRadius: '4px',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            width: `${slackUploadStatus?.progress || 0}%`,
                            height: '100%',
                            backgroundColor: '#2196f3',
                            borderRadius: '4px',
                            transition: 'width 0.3s ease',
                          }}
                        />
                      </div>

                      <Flex direction="row" justify="space-between" align="center">
                        <div style={{ color: '#666' }}>
                          <Text fontSize="sm">{formatElapsedTime(elapsedTime || 0)} elapsed</Text>
                        </div>
                        <button
                          onClick={resetSlackUpload}
                          style={{
                            backgroundColor: '#f44336',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            padding: '6px 12px',
                            fontSize: '12px',
                            cursor: 'pointer',
                          }}
                        >
                          Cancel
                        </button>
                      </Flex>
                    </Flex>
                  </div>
                )}

                {/* Completed State */}
                {slackUploadStatus?.completed && (
                  <div
                    style={{
                      backgroundColor: '#e8f5e8',
                      padding: '16px',
                      borderRadius: '8px',
                      border: '1px solid #4caf50',
                    }}
                  >
                    <Flex direction="column" gap={8}>
                      <div style={{ color: '#2e7d32' }}>
                        <Text fontSize="md">✅ Slack export uploaded successfully!</Text>
                      </div>
                      <div style={{ color: '#666' }}>
                        <Text fontSize="sm">
                          {slackUploadStatus?.filename} is being processed. Try asking your Slackbot
                          some questions!
                        </Text>
                      </div>
                    </Flex>
                  </div>
                )}
              </>
            )}

            {/* Previous Exports List */}
            {slackExports && slackExports.length > 0 && <SlackExportsList exports={slackExports} />}
          </Flex>
        );
      },
    },
  ],
  github: [
    {
      title: 'Create Personal Access Token',
      content: ({ linkClickStates: _linkClickStates, onLinkClick }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Create Personal Access Token</span>
          </Text>
          <LinkRequiredStep
            descriptionBefore="Visit"
            linkText="GitHub token creation page"
            linkUrl="https://github.com/settings/personal-access-tokens/new"
            onLinkClick={() => onLinkClick?.('createToken')}
            descriptionAfter="to create a GitHub Personal Access Token (PAT)"
          />
        </Flex>
      ),
      requiresInput: true,
      requiresLinkClick: true,
      validateInput: (_value, _inputValue, _hasError, linkClickStates) => {
        return Boolean(linkClickStates?.createToken);
      },
    },
    {
      title: 'Configure Token Details',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">
            Choose a token name, make sure to choose your organization under "Resource owner," and
            set the maximum expiration
          </Text>
          <img
            src={githubTokenConfig}
            alt="Token configuration with name, resource owner, and expiration"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Set Repository Access',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">Select access to "all repositories"</Text>
          <img
            src={githubRepoAccess}
            alt="Repository access selection showing all repositories option"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Configure Permissions',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">
            Configure the proper permissions. <strong>Important:</strong> select "Read and write"
            for Webhooks
          </Text>
          <img
            src={githubPermissions}
            alt="Permissions settings with Webhooks set to Read and write"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Copy Personal Access Token',
      content: ({ inputValue, onInputChange, hasError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">Copy the personal access token and paste it below</Text>
          <img
            src={githubTokenGenerated}
            alt="Generated token with copy option"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Input
            placeholder="ghp_... or github_pat_..."
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            error={
              hasError && inputValue
                ? 'Please enter a valid GitHub Personal Access Token starting with "ghp_" or "github_pat_"'
                : undefined
            }
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        if (!value.startsWith('ghp_') && !value.startsWith('github_pat_')) return false;
        if (value.length < 20) return false;
        return true;
      },
    },
    {
      title: 'Navigate to Organization Settings',
      content: ({ linkClickStates: _linkClickStates, onLinkClick }) => (
        <LinkRequiredStep
          descriptionBefore="Go to"
          linkText="GitHub Organizations"
          linkUrl="https://github.com/settings/organizations"
          onLinkClick={() => onLinkClick?.('organizationSettings')}
          descriptionAfter='and click "Settings" for your organization'
          additionalContent={
            <img
              src={githubOrgSettings}
              alt="GitHub organizations page with Settings button"
              style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
            />
          }
        />
      ),
      requiresInput: true,
      requiresLinkClick: true,
      validateInput: (_value, _inputValue, _hasError, linkClickStates) => {
        return Boolean(linkClickStates?.organizationSettings);
      },
    },
    {
      title: 'Create Webhook',
      content: (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">
            In the organization settings sidebar, click on "Webhooks" and then click "Add webhook"
          </Text>
          <img
            src={githubWebhooksPage}
            alt="GitHub webhooks page with Add webhook button"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
    {
      title: 'Configure Webhook',
      content: ({ webhookUrls, onCopyWebhookUrl: _onCopyWebhookUrl }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">Fill in the webhook configuration as shown:</Text>
          <div
            style={{
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: 8,
              border: '1px solid #e0e0e0',
            }}
          >
            <Text fontSize="sm">
              <strong>Payload URL:</strong>
            </Text>
            <div
              style={{
                backgroundColor: 'white',
                padding: '8px',
                borderRadius: 4,
                border: '1px solid #ddd',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                {webhookUrls?.GITHUB || 'Loading...'}
              </code>
              <CopyButton textToCopy={webhookUrls?.GITHUB || ''} disabled={!webhookUrls?.GITHUB} />
            </div>
          </div>
          <Badge color="accent" text="Content type: application/json" />
          <Badge color="accent" text="Events: Send me everything" />
          <img
            src={githubWebhookConfig}
            alt="GitHub webhook configuration form with all fields filled"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
    },
  ],
  linear: [
    {
      title: 'Navigate to Security Settings',
      content: ({ linkClickStates: _linkClickStates, onLinkClick }) => (
        <LinkRequiredStep
          descriptionBefore="Visit"
          linkText="Linear Security & Access settings page"
          linkUrl="https://linear.app/settings/account/security"
          onLinkClick={() => onLinkClick?.('securitySettings')}
          descriptionAfter="and create a new API Key (ensure it has Read permissions)"
          size="md"
          additionalContent={
            <img
              src={linearApiKeyCreation}
              alt="API Key creation with Read permissions"
              style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
            />
          }
        />
      ),
      requiresInput: true,
      requiresLinkClick: true,
      validateInput: (_value, _inputValue, _hasError, linkClickStates) => {
        return Boolean(linkClickStates?.securitySettings);
      },
    },
    {
      title: 'Copy API Key',
      content: ({ inputValue, onInputChange, hasError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">Copy and paste the API key below</Text>
          <img
            src={linearApiKeyGenerated}
            alt="Generated API key with copy option"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Input
            placeholder="lin_api_..."
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            type="password"
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
            error={
              hasError && inputValue
                ? 'Please enter a valid Linear API key starting with "lin_api_"'
                : undefined
            }
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        if (!value.startsWith('lin_api_')) return false;
        if (value.length < 20) return false;
        return true;
      },
    },
    {
      title: 'Navigate to API Settings',
      content: ({ linkClickStates: _linkClickStates, onLinkClick }) => (
        <LinkRequiredStep
          descriptionBefore="Next, visit"
          linkText="Linear API settings page"
          linkUrl="https://linear.app/settings/api"
          onLinkClick={() => onLinkClick?.('apiSettings')}
          descriptionAfter="and create a new Webhook"
          additionalContent={
            <img
              src={linearWebhookCreation}
              alt="Webhook creation interface"
              style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
            />
          }
        />
      ),
      requiresInput: true,
      requiresLinkClick: true,
      validateInput: (_value, _inputValue, _hasError, linkClickStates) => {
        return Boolean(linkClickStates?.apiSettings);
      },
    },
    {
      title: 'Configure Webhook',
      content: ({
        webhookUrls,
        onCopyWebhookUrl: _onCopyWebhookUrl,
        inputValue,
        onInputChange,
        hasError,
      }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="md">
            Configure webhook to support Comments, Users, Issues, and Projects with the following
            URL
          </Text>
          <div
            style={{
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: 8,
              border: '1px solid #e0e0e0',
            }}
          >
            <Text fontSize="sm">
              <strong>Webhook URL:</strong>
            </Text>
            <div
              style={{
                backgroundColor: 'white',
                padding: '8px',
                borderRadius: 4,
                border: '1px solid #ddd',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                {webhookUrls?.LINEAR || 'Loading...'}
              </code>
              <CopyButton textToCopy={webhookUrls?.LINEAR || ''} disabled={!webhookUrls?.LINEAR} />
            </div>
          </div>
          <img
            src={linearWebhookConfig}
            alt="Webhook configuration with URL and settings"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
          <Input
            placeholder="Signing secret from Linear webhook"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            type="password"
            autoComplete="off"
            data-form-type="other"
            data-lpignore="true"
            data-1p-ignore="true"
            error={
              hasError && inputValue
                ? 'Please enter a valid Linear webhook signing secret'
                : undefined
            }
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        if (value.length < 10) return false;
        return true;
      },
    },
  ],
  google_email: [
    {
      title: 'Create Client',
      content: ({ clientId }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Create Client</span>
          </Text>

          {/* Step 1: Link to Console */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">
              1. Go to the{' '}
              <a
                href="https://admin.google.com/ac/owl/domainwidedelegation"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#007bff', textDecoration: 'underline' }}
              >
                Domain-wide Delegation section
              </a>{' '}
              in the Google Admin Console
            </Text>
          </Flex>

          {/* Step 2: Image showing "Add Client" */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">2. Click "Add new" to create a new client:</Text>
            <img
              src={googleAddClient}
              alt="Add Client button in Google Admin Console"
              style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
            />
          </Flex>

          {/* Step 3: Client ID */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">
              3. Use this Client ID that has been automatically generated for you:
            </Text>
            {!clientId ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px',
                  backgroundColor: '#f5f5f5',
                  borderRadius: 8,
                  border: '1px solid #e0e0e0',
                }}
              >
                <span
                  style={{
                    display: 'inline-block',
                    width: '16px',
                    height: '16px',
                    border: '2px solid #007bff',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    marginRight: '8px',
                  }}
                ></span>
                <Text fontSize="sm">Generating service account...</Text>
              </div>
            ) : (
              <div
                style={{
                  backgroundColor: '#f5f5f5',
                  padding: '12px',
                  borderRadius: 8,
                  border: '1px solid #e0e0e0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                }}
              >
                <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                  {clientId}
                </code>
                <CopyButton textToCopy={clientId || ''} disabled={!clientId} />
              </div>
            )}
          </Flex>

          {/* Step 4: OAuth Scopes */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">4. Add these OAuth scopes, then click "Authorize":</Text>
            <div
              style={{
                backgroundColor: '#f5f5f5',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #e0e0e0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/gmail.readonly
              </code>
              <CopyButton textToCopy="https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/gmail.readonly" />
            </div>
          </Flex>
          <img
            src={googleAddClientId}
            alt="Add Client ID in Google Admin Console"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (_value, _inputValue, _hasError, _linkClickStates, clientId) => {
        // For Google Email, we just need the client ID to be available
        return Boolean(clientId);
      },
    },
    {
      title: 'Enter Admin Email',
      content: ({ inputValue, onInputChange, hasError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Enter Admin Email</span>
          </Text>
          <Text fontSize="md">Enter email of Google Workspace admin:</Text>
          <Input
            placeholder="admin@example.com"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            error={hasError && inputValue ? 'Please enter a valid email address' : undefined}
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(value.trim());
      },
    },
  ],
  google_drive: [
    {
      title: 'Create Client',
      content: ({ clientId }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Create Client</span>
          </Text>

          {/* Step 1: Link to Console */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">
              1. Go to the{' '}
              <a
                href="https://admin.google.com/ac/owl/domainwidedelegation"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#007bff', textDecoration: 'underline' }}
              >
                Domain-wide Delegation section
              </a>{' '}
              in the Google Admin Console
            </Text>
            <Text fontSize="sm" color="tertiary">
              <strong>Important:</strong> Only files accessible domain-wide will be indexed
            </Text>
          </Flex>

          {/* Step 2: Image showing "Add Client" */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">2. Click "Add new" to create a new client:</Text>
            <img
              src={googleAddClient}
              alt="Add Client button in Google Admin Console"
              style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
            />
          </Flex>

          {/* Step 3: Client ID */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">
              3. Use this Client ID that has been automatically generated for you:
            </Text>
            {!clientId ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px',
                  backgroundColor: '#f5f5f5',
                  borderRadius: 8,
                  border: '1px solid #e0e0e0',
                }}
              >
                <span
                  style={{
                    display: 'inline-block',
                    width: '16px',
                    height: '16px',
                    border: '2px solid #007bff',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    marginRight: '8px',
                  }}
                ></span>
                <Text fontSize="sm">Generating service account...</Text>
              </div>
            ) : (
              <div
                style={{
                  backgroundColor: '#f5f5f5',
                  padding: '12px',
                  borderRadius: 8,
                  border: '1px solid #e0e0e0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                }}
              >
                <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                  {clientId}
                </code>
                <CopyButton textToCopy={clientId || ''} disabled={!clientId} />
              </div>
            )}
          </Flex>

          {/* Step 4: OAuth Scopes */}
          <Flex direction="column" gap={8}>
            <Text fontSize="md">4. Add these OAuth scopes, then click "Authorize":</Text>
            <div
              style={{
                backgroundColor: '#f5f5f5',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #e0e0e0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <code style={{ fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all' }}>
                https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/drive.readonly
              </code>
              <CopyButton textToCopy="https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/drive.readonly" />
            </div>
          </Flex>
          <img
            src={googleAddClientId}
            alt="Add Client ID in Google Admin Console"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (_value, _inputValue, _hasError, _linkClickStates, clientId) => {
        // For Google Drive, we just need the client ID to be available
        return Boolean(clientId);
      },
    },
    {
      title: 'Enter Admin Email',
      content: ({ inputValue, onInputChange, hasError }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Enter Admin Email</span>
          </Text>
          <Text fontSize="md">Enter email of Google Workspace admin:</Text>
          <Input
            placeholder="admin@example.com"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            error={hasError && inputValue ? 'Please enter a valid email address' : undefined}
          />
        </Flex>
      ),
      requiresInput: true,
      validateInput: (value: string) => {
        if (!value.trim()) return false;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(value.trim());
      },
    },
  ],
  salesforce: [
    {
      title: 'Enable Change Data Capture (CDC)',
      content: ({ linkClickStates: _linkClickStates, onLinkClick: _onLinkClick }) => (
        <Flex direction="column" gap={16}>
          <Text fontSize="lg">
            <span style={{ fontWeight: 'bold' }}>Enable Change Data Capture (CDC)</span>
          </Text>
          <Text fontSize="md">
            For real-time updates when your Salesforce data changes, you need to enable{' '}
            <strong>Change Data Capture</strong> for the objects you want Grapevine to track.
          </Text>

          <div
            style={{
              backgroundColor: '#fff3cd',
              padding: '12px',
              borderRadius: 8,
              border: '1px solid #ffeaa7',
            }}
          >
            <Text fontSize="sm">
              <strong>Important:</strong> You must enable CDC for each object type that you want
              Grapevine to receive live updates for. Objects without CDC enabled will only be synced
              during initial backfill.
            </Text>
          </div>

          <Flex direction="column" gap={8}>
            <Text fontSize="md" fontWeight="semibold">
              Currently Supported Objects:
            </Text>
            <Flex direction="column" gap={4} pl={16}>
              <Text fontSize="md">• Account</Text>
              <Text fontSize="md">• Contact</Text>
              <Text fontSize="md">• Opportunity</Text>
              <Text fontSize="md">• Lead</Text>
              <Text fontSize="md">• Case</Text>
            </Flex>
          </Flex>

          <Flex direction="column" gap={8}>
            <Text fontSize="md" fontWeight="semibold">
              How to Enable CDC:
            </Text>
            <Text fontSize="md">
              {/* eslint-disable-next-line verb-nouns/no-verb-noun-confusion */}
              1. In the Salesforce org you want to connect, navigate to <strong>
                Setup
              </strong> → <strong>Change Data Capture</strong>
            </Text>
            <Text fontSize="md">
              2. Select all 5 object types listed above and click <strong>Save</strong>. We
              recommend enabling CDC for all objects.
            </Text>
          </Flex>

          <img
            src={salesforceCdc}
            alt="Salesforce Change Data Capture interface with required entities selected"
            style={{ width: '100%', borderRadius: 8, border: '1px solid #e0e0e0' }}
          />
        </Flex>
      ),
      requiresInput: false,
      requiresLinkClick: false,
      validateInput: () => true,
    },
    {
      title: 'Authenticate with Salesforce',
      content: (props: { onLinkClick?: (linkKey: string) => void }) => {
        const { onLinkClick } = props;
        return (
          <Flex direction="column" gap={16}>
            <Text fontSize="lg">
              <span style={{ fontWeight: 'bold' }}>Authenticate with Salesforce</span>
            </Text>
            <Text fontSize="md">
              Connect your Salesforce org to automatically sync and index your data.
            </Text>

            {/* Requirements Section */}
            <Flex direction="column" gap={8}>
              <Text fontSize="md" fontWeight="semibold">
                Requirements:
              </Text>
              <Flex direction="column" gap={4} pl={16}>
                <Text fontSize="md">• System Administrator role or equivalent privileges</Text>
              </Flex>
            </Flex>

            {/* Best Practices Section */}
            <div
              style={{
                backgroundColor: '#d4edda',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #c3e6cb',
              }}
            >
              <Text fontSize="sm" fontWeight="bold">
                💡 Best Practice: Dedicated Service Account
              </Text>
              <br />
              <Text fontSize="sm">
                We recommend creating a dedicated system admin service account for this connection.
                Using an account associated with an employee can lead to data access disruptions if
                the employee leaves the company or the account is disabled.
              </Text>
            </div>

            {/* API Usage Information */}
            <div
              style={{
                backgroundColor: '#e3f2fd',
                padding: '12px',
                borderRadius: 8,
              }}
            >
              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="bold">
                  API Usage Info
                </Text>
                <Text fontSize="sm">
                  Grapevine uses the Salesforce{' '}
                  <a
                    href="https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_rest.htm"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#007bff', textDecoration: 'underline' }}
                  >
                    REST API
                  </a>{' '}
                  via{' '}
                  <a
                    href="https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql.htm"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#007bff', textDecoration: 'underline' }}
                  >
                    SOQL
                  </a>{' '}
                  queries to ingest your data:
                </Text>
                <Flex direction="column" gap={4} pl={16}>
                  <Text fontSize="sm">
                    • <strong>Initial backfill:</strong> 1 API call per ~200 objects
                  </Text>
                  <Text fontSize="sm">
                    • <strong>Live updates:</strong> 1 API call per changed object (when CDC
                    notifies us)
                  </Text>
                </Flex>
              </Flex>
            </div>

            {/* Currently Supported Objects */}
            <Flex direction="column" gap={8} mb={8}>
              <Text fontSize="md" fontWeight="semibold">
                Currently Supported Objects:
              </Text>
              <Flex direction="column" gap={4} pl={16}>
                <Text fontSize="md">• Accounts</Text>
                <Text fontSize="md">• Contacts</Text>
                <Text fontSize="md">• Opportunities</Text>
                <Text fontSize="md">• Leads</Text>
                <Text fontSize="md">• Cases</Text>
              </Flex>
              <Text fontSize="md">
                Initial data backfill is currently limited to{' '}
                <strong>50,000 objects per object type</strong>. All new and modified records with
                CDC enabled (from the previous step) will still be synced.
              </Text>
            </Flex>

            <button
              onClick={() => onLinkClick?.('authenticateSalesforce')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '12px 24px',
                backgroundColor: '#1589F0',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
                textDecoration: 'none',
              }}
            >
              Connect to Salesforce
            </button>

            <div
              style={{
                backgroundColor: '#fff3cd',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #ffeaa7',
              }}
            >
              <Text fontSize="sm">
                <strong>Careful:</strong> Make sure you log into the correct Salesforce org with an
                appropriate user with sufficient permissions!
              </Text>
            </div>
          </Flex>
        );
      },
      requiresInput: false,
      requiresLinkClick: false,
      validateInput: () => {
        return true;
      },
    },
    {
      title: 'Connection Successful',
      content: (props) => {
        const { configData } = props;
        return (
          <Flex direction="column" gap={16}>
            <Text fontSize="lg">
              <span style={{ fontWeight: 'bold' }}>Connection Successful!</span>
            </Text>
            <div
              style={{
                backgroundColor: '#d4edda',
                padding: '12px',
                borderRadius: 8,
                border: '1px solid #c3e6cb',
              }}
            >
              <Text fontSize="sm">
                Your Salesforce account has been successfully connected.
                {configData?.SALESFORCE_INSTANCE_URL && (
                  <>
                    <br />
                    Connected to: <strong>{configData?.SALESFORCE_INSTANCE_URL}</strong>
                  </>
                )}
              </Text>
            </div>
          </Flex>
        );
      },
    },
  ],
};
