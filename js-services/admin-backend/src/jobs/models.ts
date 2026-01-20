/**
 * Zod schemas for SQS job messages.
 *
 * WARNING: These schemas must be kept in sync with the Python Pydantic models
 * in src/jobs/models.py. Any changes to the Python models must be reflected here.
 */

import { z } from 'zod';
import { ExternalSourceSchema } from '@corporate-context/backend-common';

// Base schema for all backfill ingest job configurations
export const BackfillIngestConfigSchema = z.object({
  message_type: z.literal('backfill'),
  tenant_id: z.string(),
  backfill_id: z.string().optional(),
  suppress_notification: z.boolean().optional(),
  force_update: z.boolean().optional(),
});

export const LinearApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('linear_api_backfill_root'),
});

export const LinearApiBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('linear_api_backfill'),
  issue_ids: z.array(z.string()),
  start_timestamp: z.string().datetime().optional(),
});

const GitHubPRBatchSchema = z.object({
  org_or_owner: z.string(),
  repo_name: z.string(),
  repo_id: z.number().int(),
  pr_numbers: z.array(z.number().int()),
});

export const GitHubPRBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('github_pr_backfill_root'),
  repositories: z.array(z.string()).default([]),
  organizations: z.array(z.string()).default([]),
});

export const GitHubPRBackfillRepoConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('github_pr_backfill_repo'),
  repo_full_name: z.string(),
  repo_id: z.number().int(),
});

export const GitHubPRBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('github_pr_backfill'),
  pr_batches: z.array(GitHubPRBatchSchema),
});

const GitHubFileBatchSchema = z.object({
  org_or_owner: z.string(),
  repo_name: z.string(),
  file_paths: z.array(z.string()),
  branch: z.string().optional(),
  commit_sha: z.string().optional(),
});

export const GitHubFileBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('github_file_backfill_root'),
  repositories: z.array(z.string()).default([]),
  organizations: z.array(z.string()).default([]),
});

export const GitHubFileBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('github_file_backfill'),
  file_batches: z.array(GitHubFileBatchSchema),
});

const GongWorkspacePermissionsSchema = z.object({
  workspace_id: z.string(),
  users: z.array(z.record(z.any())),
  permission_profiles: z.array(z.record(z.any())),
  permission_profile_users: z.record(z.array(z.record(z.any()))),
  library_folders: z.array(z.record(z.any())),
  call_to_folder_ids: z.record(z.array(z.string())),
});

const GongCallBatchSchema = z.object({
  call_ids: z.array(z.string()),
  workspace_id: z.string().optional(),
});

export const GongCallBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gong_call_backfill_root'),
  workspace_ids: z.array(z.string()).optional(),
  from_datetime: z.string().datetime().optional(),
  to_datetime: z.string().datetime().optional(),
  call_limit: z.number().int().positive().optional(),
  batch_size: z.number().int().positive().optional(),
});

export const GongCallBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gong_call_backfill'),
  call_batches: z.array(GongCallBatchSchema),
  from_datetime: z.string().datetime().optional(),
  to_datetime: z.string().datetime().optional(),
  workspace_permissions: GongWorkspacePermissionsSchema.optional(),
});

export const NotionApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('notion_api_backfill_root'),
  page_limit: z.number().int().positive().optional(),
});

export const NotionApiBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('notion_api_backfill'),
  page_ids: z.array(z.string()),
  start_timestamp: z.string().datetime().optional(),
});

export const NotionUserRefreshConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('notion_user_refresh'),
});

const SlackChannelDayFileSchema = z.object({
  channel_name: z.string(),
  channel_id: z.string(),
  filename: z.string(),
  start_byte: z.number().int().min(0),
  size: z.number().int().positive(),
});

export const SlackExportBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('slack_export_backfill_root'),
  uri: z.string(),
  message_limit: z.number().int().positive().optional(),
});

export const SlackExportBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('slack_export_backfill'),
  uri: z.string(),
  channel_day_files: z.array(SlackChannelDayFileSchema),
  message_limit: z.number().int().positive().optional(),
});

export const GoogleDriveDiscoveryConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('google_drive_discovery'),
});

export const GoogleEmailDiscoveryConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('google_email_discovery'),
});

export const GoogleDriveUserDriveConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('google_drive_user_drive'),
  user_email: z.string(),
  user_id: z.string(),
});

export const GoogleDriveSharedDriveConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('google_drive_shared_drive'),
  drive_id: z.string(),
  drive_name: z.string(),
});

const SalesforceObjectBatchSchema = z.object({
  object_type: z.string(),
  record_ids: z.array(z.string()),
});

export const SalesforceBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('salesforce_backfill_root'),
});

export const SalesforceBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('salesforce_backfill'),
  object_batches: z.array(SalesforceObjectBatchSchema),
});

export const HubSpotBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('hubspot_backfill_root'),
});

export const HubSpotCompanyBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('hubspot_company_backfill'),
  start_date: z.string().datetime(),
  end_date: z.string().datetime(),
});

export const HubSpotDealBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('hubspot_deal_backfill'),
  start_date: z.string().datetime(),
  end_date: z.string().datetime(),
});

export const JiraApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('jira_api_backfill_root'),
  project_keys: z.array(z.string()).default([]),
});

const JiraProjectBatchSchema = z.object({
  project_key: z.string(),
  project_id: z.string(),
  project_name: z.string(),
});

export const JiraApiBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('jira_api_backfill'),
  project_batches: z.array(JiraProjectBatchSchema),
  start_timestamp: z.string().datetime().optional(),
});

export const ConfluenceApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('confluence_api_backfill_root'),
  space_keys: z.array(z.string()).default([]),
});

const ConfluenceSpaceBatchSchema = z.object({
  space_key: z.string(),
  space_id: z.string(),
  space_name: z.string(),
});

export const ConfluenceApiBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('confluence_api_backfill'),
  space_batches: z.array(ConfluenceSpaceBatchSchema),
  start_timestamp: z.string().datetime().optional(),
});

export const GatherApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gather_api_backfill_root'),
  space_id: z.string(),
});

export const ZendeskFullBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('zendesk_full_backfill'),
});

export const TrelloApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('trello_api_backfill_root'),
});

const TrelloBoardBatchSchema = z.object({
  board_id: z.string(),
  board_name: z.string(),
});

export const TrelloApiBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('trello_api_backfill'),
  board_batches: z.array(TrelloBoardBatchSchema),
  start_timestamp: z.string().datetime().optional(),
});

export const AsanaFullBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('asana_full_backfill'),
});

export const AttioBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('attio_backfill_root'),
});

export const FirefliesFullBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('fireflies_full_backfill'),
});

export const PylonFullBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('pylon_full_backfill'),
});

export const PylonIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('pylon_incremental_backfill'),
  lookback_hours: z.number().default(2),
});

export const MondayBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('monday_backfill_root'),
});

export const PipedriveBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('pipedrive_backfill_root'),
});

export const PipedriveIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('pipedrive_incremental_backfill'),
  lookback_hours: z.number().default(2),
});

export const FigmaBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('figma_backfill_root'),
  // Optional: specific team IDs to sync. If not provided, syncs all selected teams.
  team_ids_to_sync: z.array(z.string()).optional(),
});

export const FigmaIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('figma_incremental_backfill'),
  lookback_hours: z.number().default(24),
});

export const PostHogBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('posthog_backfill_root'),
  // Optional: specific project IDs to sync. If not provided, syncs all accessible projects.
  project_ids_to_sync: z.array(z.number()).optional(),
});

export const PostHogIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('posthog_incremental_backfill'),
  lookback_hours: z.number().default(24),
});

export const CanvaBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('canva_backfill_root'),
});

export const CanvaIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('canva_incremental_backfill'),
  check_count: z.number().default(200),
});

export const TeamworkBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('teamwork_backfill_root'),
});

export const TeamworkIncrementalBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('teamwork_incremental_backfill'),
  lookback_hours: z.number().default(24),
});

export const IntercomApiBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('intercom_api_backfill_root'),
});

export const GitLabBackfillRootConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gitlab_backfill_root'),
  projects: z.array(z.string()).default([]),
  groups: z.array(z.string()).default([]),
});

// GitLab MR batch schema
const GitLabMRBatchSchema = z.object({
  project_id: z.number().int(),
  project_path: z.string(),
  mr_iids: z.array(z.number().int()),
});

export const GitLabMRBackfillProjectConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gitlab_mr_backfill_project'),
  project_id: z.number().int(),
  project_path: z.string(),
});

export const GitLabMRBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gitlab_mr_backfill'),
  mr_batches: z.array(GitLabMRBatchSchema),
});

// GitLab file batch schema
const GitLabFileBatchSchema = z.object({
  project_id: z.number().int(),
  project_path: z.string(),
  file_paths: z.array(z.string()),
  branch: z.string().optional(),
  commit_sha: z.string().optional(),
});

export const GitLabFileBackfillProjectConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gitlab_file_backfill_project'),
  project_id: z.number().int(),
  project_path: z.string(),
});

export const GitLabFileBackfillConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('gitlab_file_backfill'),
  file_batches: z.array(GitLabFileBatchSchema),
});

// Custom data document schema for ingest payload
const CustomDataDocumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
  content: z.string(),
  custom_fields: z.record(z.unknown()).optional(),
});

// Custom data ingest job - carries document payload directly
// WARNING: This must match the Python model CustomDataIngestConfig!
export const CustomDataIngestConfigSchema = BackfillIngestConfigSchema.extend({
  source: z.literal('custom_data_ingest'),
  slug: z.string(),
  documents: z.array(CustomDataDocumentSchema),
});

// Tenant data deletion message
// WARNING: This must match the Python model TenantDataDeletionMessage!
export const TenantDataDeletionMessageSchema = z.object({
  message_type: z.literal('tenant_data_deletion'),
  tenant_id: z.string(),
});

// Control message for Slack bot operations
// WARNING: This must match the Python model SlackBotControlMessage!
export const SlackBotControlMessageSchema = z.object({
  tenant_id: z.string(),
  control_type: z.enum([
    'join_all_channels',
    'refresh_bot_credentials',
    'welcome_message',
    'triage_channel_welcome',
  ]),
  source_type: z.literal('control'),
  timestamp: z.string(),
  channel_ids: z.array(z.string()).optional(), // List of channel IDs for triage_channel_welcome
});

// Sample question answerer message for triggering the sample question answerer job
export const SampleQuestionAnswererMessageSchema = z.object({
  source_type: z.literal('sample_question_answerer'),
  tenant_id: z.string(),
  timestamp: z.string(),
  iteration_count: z.number().optional(),
});

// Backfill notification message for notifying Slack bot when backfill starts
// WARNING: This must match the Python model BackfillNotificationMessage!
export const BackfillNotificationMessageSchema = z.object({
  source_type: z.literal('backfill_notification'),
  tenant_id: z.string(),
  source: ExternalSourceSchema,
});

// Backfill complete notification message for notifying Slack bot when backfill finishes
// WARNING: This must match the Python model BackfillCompleteNotificationMessage!
export const BackfillCompleteNotificationMessageSchema = z.object({
  source_type: z.literal('backfill_complete_notification'),
  tenant_id: z.string(),
  source: ExternalSourceSchema,
  backfill_id: z.string(),
});

// Reindex message for full re-indexing of a source type
// WARNING: This must match the Python model ReindexJobMessage!
export const ReindexJobMessageSchema = z.object({
  message_type: z.literal('reindex'),
  tenant_id: z.string(),
  source: z.enum([
    'slack',
    'github',
    'github_code',
    'linear',
    'notion',
    'hubspot_deal',
    'google_drive',
    'salesforce',
  ]),
  turbopuffer_only: z.boolean().default(false),
});

// Delete job message for deleting documents from search index
// WARNING: This must match the Python model DeleteJobMessage!
export const DeleteJobMessageSchema = z.object({
  message_type: z.literal('delete'),
  tenant_id: z.string(),
  document_ids: z.array(z.string()),
});
export type DeleteJobMessage = z.infer<typeof DeleteJobMessageSchema>;

// Discriminated union for backfill messages
export const BackfillIngestJobMessageSchema = z.discriminatedUnion('source', [
  LinearApiBackfillRootConfigSchema,
  LinearApiBackfillConfigSchema,
  GitHubPRBackfillRootConfigSchema,
  GitHubPRBackfillRepoConfigSchema,
  GitHubPRBackfillConfigSchema,
  GitHubFileBackfillRootConfigSchema,
  GitHubFileBackfillConfigSchema,
  GongCallBackfillRootConfigSchema,
  GongCallBackfillConfigSchema,
  NotionApiBackfillRootConfigSchema,
  NotionApiBackfillConfigSchema,
  NotionUserRefreshConfigSchema,
  SlackExportBackfillRootConfigSchema,
  SlackExportBackfillConfigSchema,
  GoogleDriveDiscoveryConfigSchema,
  GoogleEmailDiscoveryConfigSchema,
  GoogleDriveUserDriveConfigSchema,
  GoogleDriveSharedDriveConfigSchema,
  SalesforceBackfillRootConfigSchema,
  SalesforceBackfillConfigSchema,
  HubSpotBackfillRootConfigSchema,
  HubSpotCompanyBackfillConfigSchema,
  HubSpotDealBackfillConfigSchema,
  JiraApiBackfillRootConfigSchema,
  JiraApiBackfillConfigSchema,
  ConfluenceApiBackfillRootConfigSchema,
  ConfluenceApiBackfillConfigSchema,
  GatherApiBackfillRootConfigSchema,
  ZendeskFullBackfillConfigSchema,
  TrelloApiBackfillRootConfigSchema,
  TrelloApiBackfillConfigSchema,
  AsanaFullBackfillConfigSchema,
  AttioBackfillRootConfigSchema,
  FirefliesFullBackfillConfigSchema,
  PylonFullBackfillConfigSchema,
  PylonIncrementalBackfillConfigSchema,
  MondayBackfillRootConfigSchema,
  PipedriveBackfillRootConfigSchema,
  PipedriveIncrementalBackfillConfigSchema,
  FigmaBackfillRootConfigSchema,
  FigmaIncrementalBackfillConfigSchema,
  PostHogBackfillRootConfigSchema,
  PostHogIncrementalBackfillConfigSchema,
  CanvaBackfillRootConfigSchema,
  CanvaIncrementalBackfillConfigSchema,
  TeamworkBackfillRootConfigSchema,
  TeamworkIncrementalBackfillConfigSchema,
  IntercomApiBackfillRootConfigSchema,
  GitLabBackfillRootConfigSchema,
  GitLabMRBackfillProjectConfigSchema,
  GitLabMRBackfillConfigSchema,
  GitLabFileBackfillProjectConfigSchema,
  GitLabFileBackfillConfigSchema,
  CustomDataIngestConfigSchema,
]);

// Type exports
export type BackfillIngestConfig = z.infer<typeof BackfillIngestConfigSchema>;
export type LinearApiBackfillRootConfig = z.infer<typeof LinearApiBackfillRootConfigSchema>;
export type LinearApiBackfillConfig = z.infer<typeof LinearApiBackfillConfigSchema>;
export type GitHubPRBatch = z.infer<typeof GitHubPRBatchSchema>;
export type GitHubPRBackfillRootConfig = z.infer<typeof GitHubPRBackfillRootConfigSchema>;
export type GitHubPRBackfillRepoConfig = z.infer<typeof GitHubPRBackfillRepoConfigSchema>;
export type GitHubPRBackfillConfig = z.infer<typeof GitHubPRBackfillConfigSchema>;
export type GitHubFileBatch = z.infer<typeof GitHubFileBatchSchema>;
export type GitHubFileBackfillRootConfig = z.infer<typeof GitHubFileBackfillRootConfigSchema>;
export type GitHubFileBackfillConfig = z.infer<typeof GitHubFileBackfillConfigSchema>;
export type GongWorkspacePermissions = z.infer<typeof GongWorkspacePermissionsSchema>;
export type GongCallBatch = z.infer<typeof GongCallBatchSchema>;
export type GongCallBackfillRootConfig = z.infer<typeof GongCallBackfillRootConfigSchema>;
export type GongCallBackfillConfig = z.infer<typeof GongCallBackfillConfigSchema>;
export type NotionApiBackfillRootConfig = z.infer<typeof NotionApiBackfillRootConfigSchema>;
export type NotionApiBackfillConfig = z.infer<typeof NotionApiBackfillConfigSchema>;
export type NotionUserRefreshConfig = z.infer<typeof NotionUserRefreshConfigSchema>;
export type SlackChannelDayFile = z.infer<typeof SlackChannelDayFileSchema>;
export type SlackExportBackfillRootConfig = z.infer<typeof SlackExportBackfillRootConfigSchema>;
export type SlackExportBackfillConfig = z.infer<typeof SlackExportBackfillConfigSchema>;
export type GoogleDriveDiscoveryConfig = z.infer<typeof GoogleDriveDiscoveryConfigSchema>;
export type GoogleEmailDiscoveryConfig = z.infer<typeof GoogleEmailDiscoveryConfigSchema>;
export type GoogleDriveUserDriveConfig = z.infer<typeof GoogleDriveUserDriveConfigSchema>;
export type GoogleDriveSharedDriveConfig = z.infer<typeof GoogleDriveSharedDriveConfigSchema>;
export type SalesforceObjectBatch = z.infer<typeof SalesforceObjectBatchSchema>;
export type SalesforceBackfillRootConfig = z.infer<typeof SalesforceBackfillRootConfigSchema>;
export type SalesforceBackfillConfig = z.infer<typeof SalesforceBackfillConfigSchema>;
export type HubSpotBackfillRootConfig = z.infer<typeof HubSpotBackfillRootConfigSchema>;
export type HubSpotCompanyBackfillConfig = z.infer<typeof HubSpotCompanyBackfillConfigSchema>;
export type HubSpotDealBackfillConfig = z.infer<typeof HubSpotDealBackfillConfigSchema>;
export type JiraProjectBatch = z.infer<typeof JiraProjectBatchSchema>;
export type JiraApiBackfillRootConfig = z.infer<typeof JiraApiBackfillRootConfigSchema>;
export type JiraApiBackfillConfig = z.infer<typeof JiraApiBackfillConfigSchema>;
export type ConfluenceSpaceBatch = z.infer<typeof ConfluenceSpaceBatchSchema>;
export type ConfluenceApiBackfillRootConfig = z.infer<typeof ConfluenceApiBackfillRootConfigSchema>;
export type ConfluenceApiBackfillConfig = z.infer<typeof ConfluenceApiBackfillConfigSchema>;
export type GatherApiBackfillRootConfig = z.infer<typeof GatherApiBackfillRootConfigSchema>;
export type ZendeskFullBackfillConfig = z.infer<typeof ZendeskFullBackfillConfigSchema>;
export type TrelloBoardBatch = z.infer<typeof TrelloBoardBatchSchema>;
export type TrelloApiBackfillRootConfig = z.infer<typeof TrelloApiBackfillRootConfigSchema>;
export type TrelloApiBackfillConfig = z.infer<typeof TrelloApiBackfillConfigSchema>;
export type AsanaFullBackfillConfig = z.infer<typeof AsanaFullBackfillConfigSchema>;
export type AttioBackfillRootConfig = z.infer<typeof AttioBackfillRootConfigSchema>;
export type FirefliesFullBackfillConfig = z.infer<typeof FirefliesFullBackfillConfigSchema>;
export type PylonFullBackfillConfig = z.infer<typeof PylonFullBackfillConfigSchema>;
export type PylonIncrementalBackfillConfig = z.infer<typeof PylonIncrementalBackfillConfigSchema>;
export type MondayBackfillRootConfig = z.infer<typeof MondayBackfillRootConfigSchema>;
export type PipedriveBackfillRootConfig = z.infer<typeof PipedriveBackfillRootConfigSchema>;
export type PipedriveIncrementalBackfillConfig = z.infer<
  typeof PipedriveIncrementalBackfillConfigSchema
>;
export type FigmaBackfillRootConfig = z.infer<typeof FigmaBackfillRootConfigSchema>;
export type FigmaIncrementalBackfillConfig = z.infer<typeof FigmaIncrementalBackfillConfigSchema>;
export type PostHogBackfillRootConfig = z.infer<typeof PostHogBackfillRootConfigSchema>;
export type PostHogIncrementalBackfillConfig = z.infer<
  typeof PostHogIncrementalBackfillConfigSchema
>;
export type CanvaBackfillRootConfig = z.infer<typeof CanvaBackfillRootConfigSchema>;
export type CanvaIncrementalBackfillConfig = z.infer<typeof CanvaIncrementalBackfillConfigSchema>;
export type TeamworkBackfillRootConfig = z.infer<typeof TeamworkBackfillRootConfigSchema>;
export type TeamworkIncrementalBackfillConfig = z.infer<
  typeof TeamworkIncrementalBackfillConfigSchema
>;
export type IntercomApiBackfillRootConfig = z.infer<typeof IntercomApiBackfillRootConfigSchema>;
export type GitLabBackfillRootConfig = z.infer<typeof GitLabBackfillRootConfigSchema>;
export type GitLabMRBatch = z.infer<typeof GitLabMRBatchSchema>;
export type GitLabMRBackfillProjectConfig = z.infer<typeof GitLabMRBackfillProjectConfigSchema>;
export type GitLabMRBackfillConfig = z.infer<typeof GitLabMRBackfillConfigSchema>;
export type GitLabFileBatch = z.infer<typeof GitLabFileBatchSchema>;
export type GitLabFileBackfillProjectConfig = z.infer<typeof GitLabFileBackfillProjectConfigSchema>;
export type GitLabFileBackfillConfig = z.infer<typeof GitLabFileBackfillConfigSchema>;
export type CustomDataDocument = z.infer<typeof CustomDataDocumentSchema>;
export type CustomDataIngestConfig = z.infer<typeof CustomDataIngestConfigSchema>;

export type TenantDataDeletionMessage = z.infer<typeof TenantDataDeletionMessageSchema>;

export type SlackBotControlMessage = z.infer<typeof SlackBotControlMessageSchema>;
export type SampleQuestionAnswererMessage = z.infer<typeof SampleQuestionAnswererMessageSchema>;
export type BackfillNotificationMessage = z.infer<typeof BackfillNotificationMessageSchema>;
export type BackfillCompleteNotificationMessage = z.infer<
  typeof BackfillCompleteNotificationMessageSchema
>;

export type ReindexJobMessage = z.infer<typeof ReindexJobMessageSchema>;
export type BackfillIngestJobMessage = z.infer<typeof BackfillIngestJobMessageSchema>;

// NOTE: This is missing WebhookIngestJobMessage, but we only send that from python code
export type IngestJobMessage =
  | BackfillIngestJobMessage
  | ReindexJobMessage
  | TenantDataDeletionMessage;

// DocumentSource enum for indexing (matches Python DocumentSource)
// WARNING: This must match the Python enum in connectors/base/document_source.py
export const DocumentSourceSchema = z.enum([
  'slack',
  'github',
  'github_code',
  'linear',
  'notion',
  'hubspot_deal',
  'hubspot_ticket',
  'hubspot_company',
  'hubspot_contact',
  'google_drive',
  'google_email',
  'salesforce',
  'jira',
  'confluence',
  'custom',
  'custom_data',
  'gong',
  'gather',
  'trello',
  'zendesk_ticket',
  'zendesk_article',
  'asana_task',
  'intercom',
  'attio_company',
  'attio_person',
  'attio_deal',
  'fireflies_transcript',
  'gitlab_mr',
  'gitlab_code',
  'pylon_issue',
  'monday_item',
  'pipedrive_deal',
  'pipedrive_person',
  'pipedrive_organization',
  'pipedrive_product',
  'clickup_task',
  'figma_file',
  'figma_comment',
  'posthog_dashboard',
  'posthog_insight',
  'posthog_feature_flag',
  'posthog_annotation',
  'posthog_experiment',
  'posthog_survey',
  'canva_design',
  'teamwork_task',
]);
export type DocumentSource = z.infer<typeof DocumentSourceSchema>;

// Index job message for triggering index jobs via SQS
// WARNING: This must match the Python model IndexJobMessage!
export const IndexJobMessageSchema = z.object({
  entity_ids: z.array(z.string()),
  source: DocumentSourceSchema,
  tenant_id: z.string(),
  force_reindex: z.boolean().default(false),
  turbopuffer_only: z.boolean().default(false),
  backfill_id: z.string().optional(),
  suppress_notification: z.boolean().default(false),
});
export type IndexJobMessage = z.infer<typeof IndexJobMessageSchema>;
