/**
 * Lane assignments for queue jobs via SQS message_group_id to better isolate job load across tenants/sources/types.
 * See more: https://www.notion.so/gathertown/Grapevine-Lanes-v1-25ebc7eac3d180a2861efc650c582ee1?source=copy_link
 *
 * WARNING: This must be kept in sync with the Python implementation in src/jobs/lanes.py
 */

import type {
  IngestJobMessage,
  DeleteJobMessage,
  SlackBotControlMessage,
  SampleQuestionAnswererMessage,
  BackfillNotificationMessage,
  BackfillCompleteNotificationMessage,
} from './models.js';

// Effectively infinite lane count
const INFINITY_LANE_COUNT = 9999999;

// # lanes per tenant per source for backfill ingest
const INGEST_BACKFILL_TENANT_SOURCE_LANE_COUNT = 30;

/**
 * Get the ingest lane for a given ingest job message.
 */
export function getIngestLane(jobMessage: IngestJobMessage): string {
  const tenantId = jobMessage.tenant_id;

  if (jobMessage.message_type === 'backfill') {
    // Backfill = X lanes per tenant per source
    return `ingest_backfill_${tenantId}_${jobMessage.source}_${randLane(INGEST_BACKFILL_TENANT_SOURCE_LANE_COUNT)}`;
  } else if (jobMessage.message_type === 'reindex') {
    // Reindex = infinite lanes
    return `reindex_${tenantId}_${jobMessage.source}_${randLane(INFINITY_LANE_COUNT)}`;
  } else if (jobMessage.message_type === 'tenant_data_deletion') {
    // Tenant data deletion = single lane per tenant to ensure sequential processing
    return `tenant_data_deletion_${tenantId}`;
  } else {
    // TypeScript exhaustiveness check
    const _exhaustive: never = jobMessage;
    throw new Error(
      `Unknown message type: ${(_exhaustive as Record<string, unknown>).message_type}`
    );
  }
}

/**
 * Get the slackbot lane for a given slackbot job message.
 */
export function getSlackbotLane(
  jobMessage:
    | SlackBotControlMessage
    | SampleQuestionAnswererMessage
    | BackfillNotificationMessage
    | BackfillCompleteNotificationMessage
): string {
  // Slackbot = infinite lanes. TODO: this should eventually be a separate group per message_ts or something like that
  return `slackbot_${jobMessage.tenant_id}_${randLane(INFINITY_LANE_COUNT)}`;
}

/**
 * Get the delete lane for a given delete job message.
 *
 * Delete jobs go to the index jobs queue (same as index jobs) but need their own lane
 * because SQS FIFO requires MessageGroupId for ordering. Using a single lane per tenant
 * ensures sequential processing of deletes (vs index jobs which use 30 parallel lanes).
 */
export function getDeleteLane(jobMessage: DeleteJobMessage): string {
  return `delete_${jobMessage.tenant_id}`;
}

/**
 * Generate a random lane number between 0 and laneCount-1 (inclusive).
 */
function randLane(laneCount: number): number {
  return Math.floor(Math.random() * laneCount);
}
