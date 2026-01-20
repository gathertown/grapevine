"""Teamwork backfill configuration models."""

from connectors.base.models import BackfillIngestConfig


class TeamworkBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Teamwork full backfill root job."""

    source: str = "teamwork_backfill_root"


class TeamworkTaskBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for processing batches of Teamwork task IDs."""

    source: str = "teamwork_task_backfill"
    task_ids: tuple[int, ...]
    suppress_notification: bool = True


class TeamworkIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Teamwork incremental backfill job."""

    source: str = "teamwork_incremental_backfill"
    lookback_hours: int = 24
    suppress_notification: bool = True
