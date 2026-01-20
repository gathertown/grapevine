/**
 * SQS Client Initialization and simple send helpers
 *
 * Pattern-matched from existing Node services in this repo.
 */

import { SQSClient, SendMessageCommand, SendMessageCommandInput } from '@aws-sdk/client-sqs';
import { randomUUID } from 'crypto';

import { getSqsExtendedClient } from './sqs-extended-client.js';
import {
  BackfillIngestJobMessage,
  type LinearApiBackfillRootConfig,
  type GitHubPRBackfillRootConfig,
  type GitHubFileBackfillRootConfig,
  type GongCallBackfillRootConfig,
  type GoogleDriveDiscoveryConfig,
  type GoogleEmailDiscoveryConfig,
  type NotionApiBackfillRootConfig,
  type NotionUserRefreshConfig,
  type SalesforceBackfillRootConfig,
  type SlackExportBackfillRootConfig,
  type SlackBotControlMessage,
  type SampleQuestionAnswererMessage,
  type HubSpotBackfillRootConfig,
  type GatherApiBackfillRootConfig,
  type TrelloApiBackfillRootConfig,
  type TenantDataDeletionMessage,
  type BackfillNotificationMessage,
  type ZendeskFullBackfillConfig,
  type AsanaFullBackfillConfig,
  type AttioBackfillRootConfig,
  type FirefliesFullBackfillConfig,
  type PylonFullBackfillConfig,
  type PylonIncrementalBackfillConfig,
  type MondayBackfillRootConfig,
  type PipedriveBackfillRootConfig,
  type PipedriveIncrementalBackfillConfig,
  type FigmaBackfillRootConfig,
  type FigmaIncrementalBackfillConfig,
  type PostHogBackfillRootConfig,
  type PostHogIncrementalBackfillConfig,
  type CanvaBackfillRootConfig,
  type CanvaIncrementalBackfillConfig,
  type TeamworkBackfillRootConfig,
  type TeamworkIncrementalBackfillConfig,
  type IntercomApiBackfillRootConfig,
  type GitLabBackfillRootConfig,
  type CustomDataIngestConfig,
  type CustomDataDocument,
  type DeleteJobMessage,
} from './models.js';
import { getIngestLane, getSlackbotLane, getDeleteLane } from './lanes.js';
import { logger, LogContext } from '../utils/logger.js';
import { CUSTOM_DATA_INGEST_SOURCE } from '../connectors/custom-data/custom-data-constants.js';

/**
 * TODO @vic centralize with slack-bot/src/jobs/SQSJobProcessor.ts
 *
 * Convert various queue identifiers into a queue URL expected by AWS SDK
 * - If HTTPS URL, return as-is
 * - If ARN (arn:aws:sqs:region:account-id:queue-name), convert to URL
 * - If plain queue name, construct URL using AWS_REGION and AWS_ACCOUNT_ID
 */
export function arnToQueueUrl(queueIdentifier: string): string {
  // Already a full URL
  if (queueIdentifier.startsWith('https://')) {
    return queueIdentifier;
  }

  // ARN format: arn:aws:sqs:<region>:<account-id>:<queue-name>
  if (queueIdentifier.startsWith('arn:')) {
    const parts = queueIdentifier.split(':');
    if (parts.length !== 6 || parts[0] !== 'arn' || parts[1] !== 'aws' || parts[2] !== 'sqs') {
      throw new Error(`Invalid SQS ARN format: ${queueIdentifier}`);
    }
    const region = parts[3];
    const accountId = parts[4];
    const queueName = parts[5];
    return `https://sqs.${region}.amazonaws.com/${accountId}/${queueName}`;
  }

  // Plain queue name support for parity with Python services' defaults
  const region = process.env.AWS_REGION;
  const accountId = process.env.AWS_ACCOUNT_ID;
  if (!region || !accountId) {
    throw new Error(
      `Cannot resolve queue URL from plain name "${queueIdentifier}" without AWS_REGION and AWS_ACCOUNT_ID`
    );
  }
  return `https://sqs.${region}.amazonaws.com/${accountId}/${queueIdentifier}`;
}

/**
 * Specialized SQS client for sending ingest job messages with built-in validation and configuration.
 */
export class IngestSQSClient extends SQSClient {
  constructor() {
    const region = process.env.AWS_REGION;
    const endpointUrl = process.env.AWS_ENDPOINT_URL;
    const hasExplicitCreds = !!process.env.AWS_ACCESS_KEY_ID && !!process.env.AWS_SECRET_ACCESS_KEY;

    super({
      ...(region ? { region } : {}),
      ...(endpointUrl ? { endpoint: endpointUrl } : {}),
      ...(hasExplicitCreds
        ? {
            credentials: {
              accessKeyId: process.env.AWS_ACCESS_KEY_ID as string,
              secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY as string,
              ...(process.env.AWS_SESSION_TOKEN
                ? { sessionToken: process.env.AWS_SESSION_TOKEN }
                : {}),
            },
          }
        : {}),
    });

    if (endpointUrl) {
      logger.info(`SQS client configured for LocalStack at ${endpointUrl}`, {
        endpoint: endpointUrl,
      });
    }
  }

  /**
   * Get the ingest jobs queue ARN from configuration.
   * Matches the Python pattern in ingest_job_worker.py.
   */
  private getIngestJobsQueueArn(): string {
    // TODO: Read from actual config file like Python does with get_config_value()
    return process.env.INGEST_JOBS_QUEUE_ARN || 'corporate-context-ingest-jobs';
  }

  /**
   * Get the index jobs queue ARN from configuration.
   * Matches the Python pattern in index_job_worker.py.
   */
  private getIndexJobsQueueArn(): string {
    return process.env.INDEX_JOBS_QUEUE_ARN || 'corporate-context-index-jobs';
  }

  /**
   * Check if a queue ARN is the ingest jobs queue
   */
  private isIngestQueue(queueArn: string): boolean {
    const ingestQueueArn = this.getIngestJobsQueueArn();
    return queueArn === ingestQueueArn;
  }

  /**
   * Send a JSON-serializable payload to an SQS queue by ARN.
   * For the ingest queue, automatically handles large payloads via S3 if configured.
   */
  private async sendJsonMessage(
    queueArn: string,
    payload: unknown,
    messageGroupId: string,
    messageDeduplicationId?: string,
    delaySeconds?: number
  ): Promise<void> {
    const queueUrl = arnToQueueUrl(queueArn);

    let body = JSON.stringify(payload);
    let messageAttributes: Record<string, { DataType: string; StringValue: string }> | undefined;

    // For ingest queue, use extended client for large payloads
    if (this.isIngestQueue(queueArn)) {
      const extendedClient = getSqsExtendedClient();
      if (extendedClient) {
        const prepared = await extendedClient.prepareMessage(body);
        body = prepared.messageBody;
        messageAttributes = prepared.messageAttributes;
      }
    }

    const input: SendMessageCommandInput = {
      QueueUrl: queueUrl,
      MessageBody: body,
      MessageGroupId: messageGroupId,
      MessageDeduplicationId: messageDeduplicationId || randomUUID(),
      ...(delaySeconds ? { DelaySeconds: delaySeconds } : {}),
      ...(messageAttributes ? { MessageAttributes: messageAttributes } : {}),
    };

    await this.send(new SendMessageCommand(input));
  }

  /**
   * Send a Linear API backfill ingest job.
   */
  async sendLinearApiIngestJob(tenantId: string): Promise<void> {
    const config: LinearApiBackfillRootConfig = {
      message_type: 'backfill',
      source: 'linear_api_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'linear');
  }

  /**
   * Send a GitHub PR backfill ingest job.
   */
  async sendGitHubPRBackfillIngestJob(
    tenantId: string,
    options?: {
      repositories?: string[];
      organizations?: string[];
    }
  ): Promise<void> {
    const config: GitHubPRBackfillRootConfig = {
      message_type: 'backfill',
      source: 'github_pr_backfill_root',
      tenant_id: tenantId,
      repositories: options?.repositories ?? [],
      organizations: options?.organizations ?? [],
    };

    await this.sendBackfillIngestJob(config);
    // We're intentionally not sending a backfill notification here
    // because we'll send one for github file backfill that will cover both
    // kinds of Github backfills.
  }

  /**
   * Send a GitHub File backfill ingest job.
   */
  async sendGitHubFileBackfillIngestJob(
    tenantId: string,
    repositories: string[] = [],
    organizations: string[] = []
  ): Promise<void> {
    const config: GitHubFileBackfillRootConfig = {
      message_type: 'backfill',
      source: 'github_file_backfill_root',
      tenant_id: tenantId,
      repositories,
      organizations,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'github');
  }

  /**
   * Send a Gong call backfill ingest job.
   */
  async sendGongCallBackfillIngestJob(
    tenantId: string,
    options?: {
      workspaceIds?: string[];
      fromDatetime?: string;
      toDatetime?: string;
      callLimit?: number;
      batchSize?: number;
    }
  ): Promise<void> {
    const config: GongCallBackfillRootConfig = {
      message_type: 'backfill',
      source: 'gong_call_backfill_root',
      tenant_id: tenantId,
      workspace_ids: options?.workspaceIds,
      from_datetime: options?.fromDatetime,
      to_datetime: options?.toDatetime,
      call_limit: options?.callLimit,
      batch_size: options?.batchSize,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'gong');
  }

  /**
   * Send a Notion API backfill root ingest job.
   */
  async sendNotionApiIngestJob(tenantId: string, pageLimit?: number): Promise<void> {
    const config: NotionApiBackfillRootConfig = {
      message_type: 'backfill',
      source: 'notion_api_backfill_root',
      tenant_id: tenantId,
      ...(pageLimit !== undefined && { page_limit: pageLimit }),
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'notion');
  }

  /**
   * Send a Google Drive discovery job.
   */
  async sendGoogleDriveDiscoveryJob(tenantId: string): Promise<void> {
    const config: GoogleDriveDiscoveryConfig = {
      message_type: 'backfill',
      source: 'google_drive_discovery',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'google_drive');
  }

  /**
   * Send a Google Email discovery job.
   */
  async sendGoogleEmailDiscoveryJob(tenantId: string): Promise<void> {
    const config: GoogleEmailDiscoveryConfig = {
      message_type: 'backfill',
      source: 'google_email_discovery',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'google_email');
  }

  /**
   * Send a Notion User Refresh backfill ingest job.
   */
  async sendNotionUserRefreshIngestJob(tenantId: string): Promise<void> {
    const config: NotionUserRefreshConfig = {
      message_type: 'backfill',
      source: 'notion_user_refresh',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'notion');
  }

  /**
   * Send a Slack Export backfill ingest job.
   */
  async sendSlackExportIngestJob(
    tenantId: string,
    uri: string,
    messageLimit?: number
  ): Promise<void> {
    const config: SlackExportBackfillRootConfig = {
      message_type: 'backfill',
      source: 'slack_export_backfill_root',
      tenant_id: tenantId,
      uri,
      ...(messageLimit !== undefined && { message_limit: messageLimit }),
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'slack');
  }

  /**
   * Send a Salesforce backfill root ingest job.
   */
  async sendSalesforceBackfillRootIngestJob(tenantId: string): Promise<void> {
    const config: SalesforceBackfillRootConfig = {
      message_type: 'backfill',
      source: 'salesforce_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'salesforce');
  }

  /**
   * Send a HubSpot API backfill ingest job.
   */
  async sendHubSpotBackfillIngestJob(tenantId: string): Promise<void> {
    const config: HubSpotBackfillRootConfig = {
      message_type: 'backfill',
      source: 'hubspot_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'hubspot');
  }

  /**
   * Send a Gather API backfill ingest job.
   */
  async sendGatherApiIngestJob(tenantId: string, spaceId: string): Promise<void> {
    const config: GatherApiBackfillRootConfig = {
      message_type: 'backfill',
      source: 'gather_api_backfill_root',
      tenant_id: tenantId,
      space_id: spaceId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'gather');
  }

  async sendZendeskBackfillIngestJob(tenantId: string): Promise<void> {
    const config: ZendeskFullBackfillConfig = {
      message_type: 'backfill',
      source: 'zendesk_full_backfill',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'zendesk');
  }

  /**
   * Send a Trello API backfill ingest job.
   */
  async sendTrelloApiIngestJob(tenantId: string): Promise<void> {
    const config: TrelloApiBackfillRootConfig = {
      message_type: 'backfill',
      source: 'trello_api_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'trello');
  }

  async sendAsanaBackfillIngestJob(tenantId: string): Promise<void> {
    const config: AsanaFullBackfillConfig = {
      message_type: 'backfill',
      source: 'asana_full_backfill',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'asana');
  }

  /**
   * Send an Attio backfill ingest job.
   */
  async sendAttioBackfillIngestJob(tenantId: string): Promise<void> {
    const config: AttioBackfillRootConfig = {
      message_type: 'backfill',
      source: 'attio_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'attio');
  }

  async sendFirefliesBackfillIngestJob(tenantId: string): Promise<void> {
    const config: FirefliesFullBackfillConfig = {
      message_type: 'backfill',
      source: 'fireflies_full_backfill',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'fireflies');
  }

  /**
   * Send a Pylon backfill ingest job.
   */
  async sendPylonBackfillIngestJob(tenantId: string): Promise<void> {
    const config: PylonFullBackfillConfig = {
      message_type: 'backfill',
      source: 'pylon_full_backfill',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'pylon');
  }

  /**
   * Send a Pylon incremental backfill ingest job.
   * This syncs recently updated issues without doing a full backfill.
   */
  async sendPylonIncrementalBackfillJob(
    tenantId: string,
    lookbackHours: number = 2
  ): Promise<void> {
    const config: PylonIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'pylon_incremental_backfill',
      tenant_id: tenantId,
      lookback_hours: lookbackHours,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send an Intercom backfill ingest job.
   */
  async sendIntercomBackfillIngestJob(tenantId: string): Promise<void> {
    const config: IntercomApiBackfillRootConfig = {
      message_type: 'backfill',
      source: 'intercom_api_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'intercom');
  }

  /**
   * Send a Monday.com backfill ingest job.
   */
  async sendMondayBackfillIngestJob(tenantId: string): Promise<void> {
    const config: MondayBackfillRootConfig = {
      message_type: 'backfill',
      source: 'monday_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'monday');
  }

  /**
   * Send a Pipedrive backfill ingest job.
   */
  async sendPipedriveBackfillIngestJob(tenantId: string): Promise<void> {
    const config: PipedriveBackfillRootConfig = {
      message_type: 'backfill',
      source: 'pipedrive_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'pipedrive');
  }

  /**
   * Send a Pipedrive incremental backfill ingest job.
   * This syncs recently updated records without doing a full backfill.
   */
  async sendPipedriveIncrementalBackfillJob(
    tenantId: string,
    lookbackHours: number = 2
  ): Promise<void> {
    const config: PipedriveIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'pipedrive_incremental_backfill',
      tenant_id: tenantId,
      lookback_hours: lookbackHours,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send a Figma backfill ingest job.
   * @param tenantId - The tenant ID
   * @param teamIdsToSync - Optional: specific team IDs to sync. If not provided, syncs all selected teams.
   */
  async sendFigmaBackfillIngestJob(tenantId: string, teamIdsToSync?: string[]): Promise<void> {
    const config: FigmaBackfillRootConfig = {
      message_type: 'backfill',
      source: 'figma_backfill_root',
      tenant_id: tenantId,
      ...(teamIdsToSync && teamIdsToSync.length > 0 && { team_ids_to_sync: teamIdsToSync }),
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'figma');
  }

  /**
   * Send a Figma incremental backfill ingest job.
   * This syncs recently updated files without doing a full backfill.
   */
  async sendFigmaIncrementalBackfillJob(
    tenantId: string,
    lookbackHours: number = 24
  ): Promise<void> {
    const config: FigmaIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'figma_incremental_backfill',
      tenant_id: tenantId,
      lookback_hours: lookbackHours,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send a PostHog backfill ingest job.
   * @param tenantId - The tenant ID
   * @param projectIdsToSync - Optional: specific project IDs to sync. If not provided, syncs all selected projects.
   */
  async sendPostHogBackfillIngestJob(tenantId: string, projectIdsToSync?: number[]): Promise<void> {
    const config: PostHogBackfillRootConfig = {
      message_type: 'backfill',
      source: 'posthog_backfill_root',
      tenant_id: tenantId,
      ...(projectIdsToSync &&
        projectIdsToSync.length > 0 && { project_ids_to_sync: projectIdsToSync }),
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'posthog');
  }

  /**
   * Send a PostHog incremental backfill ingest job.
   * This syncs recently updated items without doing a full backfill.
   */
  async sendPostHogIncrementalBackfillJob(
    tenantId: string,
    lookbackHours: number = 24
  ): Promise<void> {
    const config: PostHogIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'posthog_incremental_backfill',
      tenant_id: tenantId,
      lookback_hours: lookbackHours,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send a Canva backfill ingest job.
   * @param tenantId - The tenant ID
   */
  async sendCanvaBackfillIngestJob(tenantId: string): Promise<void> {
    const config: CanvaBackfillRootConfig = {
      message_type: 'backfill',
      source: 'canva_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'canva');
  }

  /**
   * Send a Canva incremental backfill ingest job.
   * This syncs recently updated designs without doing a full backfill.
   */
  async sendCanvaIncrementalBackfillJob(tenantId: string, checkCount: number = 200): Promise<void> {
    const config: CanvaIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'canva_incremental_backfill',
      tenant_id: tenantId,
      check_count: checkCount,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send a Teamwork backfill ingest job.
   * @param tenantId - The tenant ID
   */
  async sendTeamworkBackfillIngestJob(tenantId: string): Promise<void> {
    const config: TeamworkBackfillRootConfig = {
      message_type: 'backfill',
      source: 'teamwork_backfill_root',
      tenant_id: tenantId,
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'teamwork');
  }

  /**
   * Send a Teamwork incremental backfill ingest job.
   * This syncs recently updated tasks without doing a full backfill.
   */
  async sendTeamworkIncrementalBackfillJob(
    tenantId: string,
    lookbackHours: number = 24
  ): Promise<void> {
    const config: TeamworkIncrementalBackfillConfig = {
      message_type: 'backfill',
      source: 'teamwork_incremental_backfill',
      tenant_id: tenantId,
      lookback_hours: lookbackHours,
      suppress_notification: true, // Don't send Slack notification for incremental syncs
    };

    await this.sendBackfillIngestJob(config);
  }

  /**
   * Send a GitLab backfill ingest job.
   * Triggers the GitLab backfill root job and sends a backfill notification.
   */
  async sendGitLabBackfillIngestJob(tenantId: string): Promise<void> {
    const config: GitLabBackfillRootConfig = {
      message_type: 'backfill',
      source: 'gitlab_backfill_root',
      tenant_id: tenantId,
      projects: [],
      groups: [],
    };

    await this.sendBackfillIngestJob(config);
    await this.sendBackfillNotification(tenantId, 'gitlab');
  }

  /**
   * Send a custom data ingest job.
   * Documents are passed directly in the message payload to be processed by the ingest worker.
   */
  async sendCustomDataIngestJob(
    tenantId: string,
    slug: string,
    documents: CustomDataDocument[]
  ): Promise<void> {
    return LogContext.run(
      {
        tenant_id: tenantId,
        slug,
        document_count: documents.length,
        operation: 'send-custom-data-ingest',
      },
      async () => {
        const config: CustomDataIngestConfig = {
          message_type: 'backfill',
          source: CUSTOM_DATA_INGEST_SOURCE,
          tenant_id: tenantId,
          slug,
          documents,
        };

        await this.sendBackfillIngestJob(config);

        logger.info(`✅ Sent custom data ingest job for ${documents.length} documents`, {
          tenant_id: tenantId,
          slug,
          document_count: documents.length,
        });
      }
    );
  }

  /**
   * Send a tenant data deletion job.
   */
  async sendTenantDataDeletionJob(tenantId: string): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'send-tenant-data-deletion' },
      async () => {
        const message: TenantDataDeletionMessage = {
          message_type: 'tenant_data_deletion',
          tenant_id: tenantId,
        };

        await this.sendJsonMessage(
          this.getIngestJobsQueueArn(),
          message,
          getIngestLane(message),
          randomUUID() // deduplication ID
        );

        logger.info(`✅ Sent tenant data deletion job for tenant ${tenantId}`);
      }
    );
  }

  /**
   * Get the Slack bot jobs queue ARN from configuration.
   */
  private getSlackJobsQueueArn(): string {
    return process.env.SLACK_JOBS_QUEUE_ARN || 'corporate-context-slack-jobs';
  }

  /**
   * Send a backfill notification message to the Slack queue.
   */
  private async sendBackfillNotification(
    tenantId: string,
    source: BackfillNotificationMessage['source']
  ): Promise<void> {
    const message: BackfillNotificationMessage = {
      source_type: 'backfill_notification',
      tenant_id: tenantId,
      source,
    };

    await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
  }

  /**
   * Send a control message to the Slack bot to join all channels.
   */
  async sendSlackBotJoinAllChannels(tenantId: string): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'send-slack-join-channels' },
      async () => {
        const message: SlackBotControlMessage = {
          tenant_id: tenantId,
          control_type: 'join_all_channels',
          source_type: 'control',
          timestamp: new Date().toISOString(),
        };

        await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
        logger.info(`✅ Sent join_all_channels control message for tenant ${tenantId}`);
      }
    );
  }

  /**
   * Send a control message to the Slack bot to refresh its credentials.
   * This causes the bot to restart its TenantSlackApp and fetch fresh bot ID.
   * This is necessary in the case where we're running a new bot, or the bot was reinstalled to the workspace.
   */
  async sendSlackBotRefreshCredentials(tenantId: string): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'send-slack-refresh-credentials' },
      async () => {
        const message: SlackBotControlMessage = {
          tenant_id: tenantId,
          control_type: 'refresh_bot_credentials',
          source_type: 'control',
          timestamp: new Date().toISOString(),
        };

        await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
        logger.info(`✅ Sent refresh_bot_credentials control message for tenant ${tenantId}`);
      }
    );
  }

  /**
   * Send a sample question answerer message to trigger the sample question answerer job.
   */
  async sendSampleQuestionAnswererJob(tenantId: string): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'send-sample-question-answerer' },
      async () => {
        const message: SampleQuestionAnswererMessage = {
          source_type: 'sample_question_answerer',
          tenant_id: tenantId,
          timestamp: new Date().toISOString(),
        };

        await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
        logger.info(`✅ Sent sample question answerer message for tenant ${tenantId}`);
      }
    );
  }

  /**
   * Send a control message to the Slack queue to send a welcome message.
   * This message is sent immediately after OAuth setup completion.
   */
  async sendSlackBotWelcomeMessage(tenantId: string): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, operation: 'send-slack-welcome-message' },
      async () => {
        const message: SlackBotControlMessage = {
          tenant_id: tenantId,
          control_type: 'welcome_message',
          source_type: 'control',
          timestamp: new Date().toISOString(),
        };

        await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
        logger.info(`✅ Sent welcome_message control message for tenant ${tenantId}`);
      }
    );
  }

  /**
   * Send a control message to the Slack queue to send welcome messages to newly mapped triage channels.
   * This message is sent after Linear team channel mappings are updated.
   */
  async sendTriageChannelWelcomeMessage(tenantId: string, channelIds: string[]): Promise<void> {
    return LogContext.run(
      {
        tenant_id: tenantId,
        operation: 'send-triage-channel-welcome',
        channel_count: channelIds.length,
      },
      async () => {
        const message: SlackBotControlMessage = {
          tenant_id: tenantId,
          control_type: 'triage_channel_welcome',
          source_type: 'control',
          timestamp: new Date().toISOString(),
          channel_ids: channelIds,
        };

        await this.sendJsonMessage(this.getSlackJobsQueueArn(), message, getSlackbotLane(message));
        logger.info(
          `✅ Sent triage_channel_welcome control message for tenant ${tenantId} with ${channelIds.length} channel(s)`
        );
      }
    );
  }

  /**
   * Send a generic backfill ingest job (for advanced usage).
   */
  async sendBackfillIngestJob(
    config: BackfillIngestJobMessage,
    messageDeduplicationId?: string
  ): Promise<void> {
    await this.sendJsonMessage(
      this.getIngestJobsQueueArn(),
      config,
      getIngestLane(config),
      messageDeduplicationId
    );
  }

  /**
   * Send a delete job message to remove documents from the search index.
   */
  async sendDeleteJob(tenantId: string, documentIds: string[]): Promise<void> {
    return LogContext.run(
      { tenant_id: tenantId, document_count: documentIds.length, operation: 'send-delete-job' },
      async () => {
        const message: DeleteJobMessage = {
          message_type: 'delete',
          tenant_id: tenantId,
          document_ids: documentIds,
        };

        await this.sendJsonMessage(
          this.getIndexJobsQueueArn(),
          message,
          getDeleteLane(message),
          randomUUID() // deduplication ID
        );

        logger.info(`✅ Sent delete job for ${documentIds.length} documents`, {
          tenant_id: tenantId,
          document_count: documentIds.length,
        });
      }
    );
  }
}

/**
 * Lazily initialized Ingest SQS client
 */
let ingestSqsClient: IngestSQSClient | null = null;

export function getSqsClient(): IngestSQSClient {
  if (!ingestSqsClient) {
    ingestSqsClient = new IngestSQSClient();
    logger.info('Ingest SQS client initialized successfully');
  }
  return ingestSqsClient;
}

/**
 * Simple check to see if SQS is likely configured
 */
export function isSqsConfigured(): boolean {
  // If either default credential chain or explicit env creds exist, we assume OK
  // This mirrors how the S3 client checks for explicit env creds
  return (
    (!!process.env.AWS_ACCESS_KEY_ID && !!process.env.AWS_SECRET_ACCESS_KEY) ||
    // Also allow running in environments where default AWS creds are injected
    !!process.env.AWS_REGION
  );
}
