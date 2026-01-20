"""PostHog extractors for backfill and incremental sync."""

from connectors.posthog.extractors.posthog_backfill_root_extractor import (
    PostHogBackfillRootExtractor,
    PostHogProjectBackfillExtractor,
)
from connectors.posthog.extractors.posthog_incremental_backfill_extractor import (
    PostHogIncrementalBackfillExtractor,
)

__all__ = [
    "PostHogBackfillRootExtractor",
    "PostHogIncrementalBackfillExtractor",
    "PostHogProjectBackfillExtractor",
]
