"""
Lane assignments for queue jobs via SQS message_group_id to better isolate job load across tenants/sources/types.
See more: https://www.notion.so/gathertown/Grapevine-Lanes-v1-25ebc7eac3d180a2861efc650c582ee1?source=copy_link

WARNING: This must be kept in sync with the TypeScript implementation in js-services/admin-backend/src/jobs/lanes.ts
"""

import random
from hashlib import md5
from typing import assert_never

from src.jobs.models import (
    BackfillCompleteNotificationMessage,
    BackfillNotificationMessage,
    DeleteJobMessage,
    IndexJobMessage,
    IngestJobMessage,
    SampleQuestionAnswererMessage,
    SlackBotControlMessage,
    WebhookIngestJobMessage,
)

# Effectively infinite lane count
INFINITY_LANE_COUNT = 9999999

# number of lanes per tenant for all webhook ingest
INGEST_WEBHOOK_TENANT_LANE_COUNT = 60
SALESFORCE_CDC_TENANT_LANE_COUNT = 60

# number of lanes per tenant per source for backfill ingest
INGEST_BACKFILL_TENANT_SOURCE_LANE_COUNT = 30

# number of lanes per tenant per source for index jobs
INDEX_TENANT_SOURCE_LANE_COUNT = 30


def get_ingest_lane(job_message: IngestJobMessage) -> str:
    """Get the ingest lane for a given ingest job message."""
    tenant_id = job_message.tenant_id

    if job_message.message_type == "webhook":
        # Webhooks = X lanes per tenant, total
        return f"ingest_webhook_{tenant_id}_{rand_lane(INGEST_WEBHOOK_TENANT_LANE_COUNT)}"
    elif job_message.message_type == "backfill":
        # Backfill = X lanes per tenant per source
        return f"ingest_backfill_{tenant_id}_{job_message.source}_{rand_lane(INGEST_BACKFILL_TENANT_SOURCE_LANE_COUNT)}"
    elif job_message.message_type == "reindex":
        # Reindex = infinite lanes
        return f"reindex_{tenant_id}_{job_message.source.value}_{rand_lane(INFINITY_LANE_COUNT)}"
    elif job_message.message_type == "tenant_data_deletion":
        # Tenant data deletion = single lane per tenant to ensure sequential processing
        return f"tenant_data_deletion_{tenant_id}"
    else:
        assert_never(job_message.message_type)


def get_salesforce_cdc_lane(tenant_id: str, unique_batch_identifier: str) -> str:
    """Get the Salesforce CDC lane for a given unique batch identifier."""
    # Consistent hash the unique batch identifier to a lane number
    lane_number = (
        int.from_bytes(md5(unique_batch_identifier.encode()).digest(), "big")
        % SALESFORCE_CDC_TENANT_LANE_COUNT
    )
    return f"ingest_cdc_{tenant_id}_{lane_number}"


def get_index_lane(job_message: IndexJobMessage) -> str:
    """Get the index lane for a given index job message."""
    # Index = X lanes per tenant per source
    return f"index_{job_message.tenant_id}_{job_message.source.value}_{rand_lane(INDEX_TENANT_SOURCE_LANE_COUNT)}"


def get_delete_lane(job_message: DeleteJobMessage) -> str:
    """Get the delete lane for a given delete job message.

    Delete jobs go to the index jobs queue (same as index jobs) but need their own lane
    because SQS FIFO requires MessageGroupId for ordering. Using a single lane per tenant
    ensures sequential processing of deletes (vs index jobs which use 30 parallel lanes).

    NOTE: Delete jobs use a different lane than index jobs, so there's no cross-lane
    ordering guarantee. During concurrent ingest/backfills, an index job could
    theoretically re-create a document after a delete job has processed it. This is a
    known limitation. A proper fix would require per-document ordering or tombstones,
    which is beyond current scope.
    """
    return f"delete_{job_message.tenant_id}"


def get_slackbot_lane(
    job_message: WebhookIngestJobMessage
    | SlackBotControlMessage
    | SampleQuestionAnswererMessage
    | BackfillNotificationMessage
    | BackfillCompleteNotificationMessage,
) -> str:
    """Get the slackbot lane for a given slackbot job message."""
    # Slackbot = infinite lanes. TODO: this should eventually be a separate group per message_ts or something like that
    return f"slackbot_{job_message.tenant_id}_{rand_lane(INFINITY_LANE_COUNT)}"


def rand_lane(lane_count: int) -> int:
    return random.randint(0, lane_count - 1)
