# Connector Ingestion Implementation Guide

This guide outlines the steps to add a new ingest/backfill connector in the backend, following the same structure we used for the updated Intercom ingest pipeline.

## Overview

```
Backfill CLI → SQS Backfill Job → Extractor → Artifacts + Indexing
```

## Step 1: Understand the Client and File Layout

### 1.1 REST Client

Every connector should expose a dedicated client under `src/clients/<service>.py`. For Intercom we use `src/clients/intercom.py`, which:

- Loads the tenant OAuth token from AWS SSM.
- Provides high-level helpers (`get_conversations`, `get_conversation`) so extractors avoid manual HTTP plumbing.
- Handles retries, logging, and rate limiting centrally.

Start by creating or updating the client so the extractor can focus purely on transforming data into artifacts.

### 1.2 File Structure (Intercom Example)

```
connectors/intercom/
├── __init__.py                               # Re-export config + extractor
├── intercom_artifacts.py                     # Artifact schema
├── intercom_conversations_extractor.py       # Backfill extractor (single entry point)
├── intercom_extractor.py                     # Base class with shared helpers
├── intercom_models.py                        # Pydantic config
src/clients/
├── intercom.py                               # REST client
scripts/
├── backfill_cli.py                           # Registers connector for the CLI
src/jobs/
├── ingest_job_worker.py                      # Maps source key → extractor + config
docs/
├── connector-ingestion-implementation-guide.md
```

Use this layout as the baseline when wiring a new connector.

## Step 2: Define the Backfill Config

Create (or extend) a Pydantic model under `connectors/<service>/<service>_models.py`. Intercom’s config shows the minimal fields you typically need:

```python
from typing import Literal
from connectors.base.models import BackfillIngestConfig

class IntercomApiConversationsBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["intercom_api_conversations_backfill"] = "intercom_api_conversations_backfill"
    conversation_ids: list[str] | None = None
    per_page: int = 150
    order: Literal["asc", "desc"] = "desc"
    starting_after: str | None = None
    max_pages: int | None = None
    max_conversations: int | None = None
```

Key ideas:

- Always inherit from `BackfillIngestConfig`.
- Include optional fields (pagination, filters) so the extractor can run in “fetch all” or “specific IDs” mode.

## Step 3: Register the Config in the CLI

Update `scripts/backfill_cli.py` so the connector can be triggered from the shared CLI. Intercom registers itself like this:

```python
from connectors.intercom.intercom_models import IntercomApiConversationsBackfillConfig

CONNECTORS = {
    # ...
    "intercom": {
        "name": "Intercom",
        "config_class": IntercomApiConversationsBackfillConfig,
        "requires_config": False,
        "description": "Backfill conversations (and parts) from Intercom",
        "config_example": {
            "conversation_ids": ["12345", "67890"],
            "per_page": 100,
            "max_conversations": 200,
        },
    },
}
```

This ensures the CLI knows which config to instantiate and shows a helpful example.

## Step 4: Wire the Extractor into the Worker

Add the extractor to the ingest worker registry and message switch. Intercom only has one entry now:

```python
from connectors.intercom import (
    IntercomApiConversationsBackfillConfig,
    IntercomConversationsBackfillExtractor,
)

self.backfill_extractors = {
    # ...
    "intercom_api_conversations_backfill": IntercomConversationsBackfillExtractor(
        self.ssm_client, self.sqs_client
    ),
}

# Message parsing
elif source == "intercom_api_conversations_backfill":
    backfill_message = IntercomApiConversationsBackfillConfig.model_validate(message_data)
```

## Step 5: Implement the Extractor

Intercom’s extractor lives in `connectors/intercom/intercom_conversations_extractor.py`. The important pieces are:

```python
class IntercomConversationsBackfillExtractor(
    IntercomExtractor[IntercomApiConversationsBackfillConfig]
):
    source_name = "intercom_api_conversations_backfill"

    async def process_job(..., config):
        if config.conversation_ids:
            await self.process_conversations_batch(...)
        else:
            await self.process_all_conversations(...)

    async def process_all_conversations(...):
        intercom_client = await self.get_intercom_client(...)
        while True:
            response = intercom_client.get_conversations(...)
            conversation_ids = [...]
            await self.process_conversations_batch(..., conversation_ids=conversation_ids, intercom_client=intercom_client)
            starting_after = response.get("pages", {}).get("next", {}).get("starting_after")
            if not starting_after:
                break

    async def process_conversations_batch(..., intercom_client=None):
        intercom_client = intercom_client or await self.get_intercom_client(...)
        for conversation_id in conversation_ids:
            response = intercom_client.get_conversation(conversation_id)
            artifact = await self.process_conversation(...)
            artifacts_to_store.append(artifact)
```

Highlights:

- **Single extractor** handles both “fetch all” and “specific IDs” flows.
- Pagination happens inside the extractor (no separate “root job” needed).
- `process_conversation` (defined in `intercom_extractor.py`) builds a typed artifact and captures metadata/timestamps.

## Step 6: Artifact Storage & Indexing

`process_conversations_batch` batches DB writes and calls `trigger_indexing` using `DocumentSource.INTERCOM`. Every connector should:

1. Build typed artifacts (metadata + source payload).
2. Store them via `store_artifacts_batch`.
3. Trigger indexing with `trigger_indexing(...)` so search stays in sync.

## Step 7: Testing & Local Backfill

1. Run the CLI locally to enqueue a backfill:

```
uv run python scripts/backfill_cli.py --tenant-id <tenant> --connector intercom
```

2. Ensure the ingest worker is running (`uv run python -m src.jobs.ingest_job_worker`).
3. Inspect `conversations.md` generated by `scripts/intercom/test_intercom_conversations.py --create-markdown` to verify end-to-end content quality.

---

By following this structure:

1. Define a config model.
2. Register the connector in the CLI and ingest worker.
3. Implement a single extractor that can paginate or process specific IDs.
4. Reuse the shared artifact helpers.

The Intercom extractor serves as a minimal, production-ready reference you can copy for future connectors.***

