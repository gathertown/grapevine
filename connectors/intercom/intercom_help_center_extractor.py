import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import IntercomArticleData
from connectors.intercom.intercom_artifacts import (
    IntercomHelpCenterArticleArtifact,
    IntercomHelpCenterArticleArtifactContent,
    IntercomHelpCenterArticleArtifactMetadata,
)
from connectors.intercom.intercom_extractor import IntercomExtractor
from connectors.intercom.intercom_models import IntercomApiHelpCenterBackfillConfig
from src.ingest.repositories import ArtifactRepository
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import get_tenant_config_value, set_tenant_config_value

logger = logging.getLogger(__name__)


class IntercomHelpCenterBackfillExtractor(IntercomExtractor[IntercomApiHelpCenterBackfillConfig]):
    """Extractor for processing Intercom Help Center article backfill jobs."""

    source_name = "intercom_api_help_center_backfill"

    async def process_job(
        self,
        job_id: str,
        config: IntercomApiHelpCenterBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Intercom Help Center articles for a tenant."""
        try:
            if config.article_ids:
                await self.process_articles_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=config.tenant_id,
                    article_ids=config.article_ids or [],
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                )
            else:
                await self.process_all_articles(
                    job_id=job_id,
                    config=config,
                    db_pool=db_pool,
                    trigger_indexing=trigger_indexing,
                )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def process_all_articles(
        self,
        job_id: str,
        config: IntercomApiHelpCenterBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Fetch and process Help Center articles for a tenant using list API with client-side filtering."""
        tenant_id = config.tenant_id
        intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id for citation URL construction
        workspace_id = await self.get_workspace_id(intercom_client)

        # Get last sync timestamp from config
        last_sync_key = "INTERCOM_HELP_CENTER_ARTICLES_LAST_SYNC_UPDATED_AT"
        last_sync_str = await get_tenant_config_value(last_sync_key, tenant_id)

        # Convert to Unix timestamp for Intercom API (they expect Unix epoch seconds)
        updated_at_after: int | None = None
        if last_sync_str:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_str)
                updated_at_after = int(last_sync_dt.timestamp())
                logger.info(
                    f"Using last sync timestamp: {last_sync_dt.isoformat()} ({updated_at_after})",
                    extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse last sync timestamp '{last_sync_str}': {e}, starting from beginning",
                    extra={"tenant_id": tenant_id},
                )
        else:
            logger.info(
                "No last sync timestamp found, will sync all articles",
                extra={"tenant_id": tenant_id},
            )

        per_page = max(1, min(config.per_page, 150))  # Intercom max is 150
        starting_after = config.starting_after
        processed_total = 0
        page_count = 0
        current_max_updated_at: int | None = None

        logger.info(
            "Starting Intercom Help Center articles backfill using list API",
            extra={
                "tenant_id": tenant_id,
                "per_page": per_page,
                "updated_at_after": updated_at_after,
                "max_pages": config.max_pages,
                "max_articles": config.max_articles,
            },
        )

        repo = ArtifactRepository(db_pool)
        entity_ids: list[str] = []

        while True:
            if config.max_pages is not None and page_count >= config.max_pages:
                logger.info(
                    "Reached max_pages limit for Intercom Help Center backfill",
                    extra={"tenant_id": tenant_id, "max_pages": config.max_pages},
                )
                break

            page_count += 1
            logger.debug(
                "Fetching Intercom Help Center articles",
                extra={
                    "tenant_id": tenant_id,
                    "page": page_count,
                    "starting_after": starting_after,
                    "updated_at_after": updated_at_after,
                },
            )

            # Always use list API (GET /articles) - the search endpoint doesn't exist
            # We'll filter by updated_at client-side if needed
            response = intercom_client.get_articles(
                per_page=per_page,
                starting_after=starting_after,
                order=config.order,
            )

            articles = response.get("data", [])
            if not articles:
                logger.info(
                    "No more articles to process",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

            # Filter articles by updated_at if we have a last sync timestamp
            if updated_at_after is not None:
                filtered_articles = []
                for article in articles:
                    article_updated_at = article.get("updated_at") or article.get("created_at")
                    if article_updated_at and int(article_updated_at) > updated_at_after:
                        filtered_articles.append(article)

                logger.debug(
                    f"Filtered {len(articles)} articles to {len(filtered_articles)} updated after {updated_at_after}",
                    extra={
                        "tenant_id": tenant_id,
                        "total": len(articles),
                        "filtered": len(filtered_articles),
                    },
                )
                articles = filtered_articles

                # If no articles match the filter, we might be done
                if not articles:
                    logger.info(
                        "No articles updated since last sync on this page",
                        extra={"tenant_id": tenant_id, "page": page_count},
                    )
                    # Continue to next page in case newer articles exist
                    # (articles might not be perfectly ordered by updated_at)

            for article_data in articles:
                if config.max_articles is not None and processed_total >= config.max_articles:
                    logger.info(
                        "Reached max_articles limit for Intercom Help Center backfill",
                        extra={
                            "tenant_id": tenant_id,
                            "max_articles": config.max_articles,
                            "processed": processed_total,
                        },
                    )
                    break

                try:
                    # Fetch full article details
                    article_id = article_data.get("id")
                    if not article_id:
                        logger.warning(
                            "Article missing ID, skipping",
                            extra={"tenant_id": tenant_id, "article_data": article_data},
                        )
                        continue

                    # Track the maximum updated_at we've seen for this article
                    article_updated_at = (
                        article_data.get("updated_at")
                        or article_data.get("updated")
                        or article_data.get("created_at")
                        or article_data.get("created")
                    )
                    if article_updated_at:
                        try:
                            # Convert to int if it's a string
                            article_updated_at_int = (
                                int(article_updated_at)
                                if isinstance(article_updated_at, str)
                                else article_updated_at
                            )
                            if (
                                current_max_updated_at is None
                                or article_updated_at_int > current_max_updated_at
                            ):
                                current_max_updated_at = article_updated_at_int
                        except (ValueError, TypeError):
                            pass

                    full_article = intercom_client.get_article(article_id)
                    artifact = await self.process_article(
                        job_id, full_article, tenant_id, db_pool, workspace_id
                    )

                    await repo.upsert_artifact(artifact)
                    entity_ids.append(artifact.entity_id)
                    processed_total += 1

                    # Trigger indexing in batches
                    if len(entity_ids) >= DEFAULT_INDEX_BATCH_SIZE:
                        await trigger_indexing(
                            entity_ids=entity_ids,
                            source=DocumentSource.INTERCOM,
                            tenant_id=tenant_id,
                            backfill_id=config.backfill_id,
                            suppress_notification=config.suppress_notification,
                        )
                        entity_ids = []

                except Exception as e:
                    logger.error(
                        f"Failed to process article {article_data.get('id')}: {e}",
                        extra={"tenant_id": tenant_id, "article_id": article_data.get("id")},
                    )
                    continue

            if config.max_articles is not None and processed_total >= config.max_articles:
                break

            # Check for pagination (per Intercom docs: pages.next is an object with starting_after)
            pages = response.get("pages")
            if not isinstance(pages, dict):
                logger.info(
                    "No more pages to process (pages is not a dict)",
                    extra={
                        "tenant_id": tenant_id,
                        "page": page_count,
                        "pages_type": type(pages).__name__,
                    },
                )
                break

            next_obj = pages.get("next")
            if not isinstance(next_obj, dict):
                logger.info(
                    "No more pages to process (no next object)",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

            starting_after = next_obj.get("starting_after")
            if not starting_after:
                logger.info(
                    "No more pages to process",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

        # Trigger indexing for remaining entities
        if entity_ids:
            await trigger_indexing(
                entity_ids=entity_ids,
                source=DocumentSource.INTERCOM,
                tenant_id=tenant_id,
                backfill_id=config.backfill_id,
                suppress_notification=config.suppress_notification,
            )

        # Update last sync timestamp to the maximum updated_at we processed
        if current_max_updated_at is not None:
            last_sync_dt = datetime.fromtimestamp(current_max_updated_at, tz=UTC)
            await set_tenant_config_value(last_sync_key, last_sync_dt.isoformat(), tenant_id)
            logger.info(
                f"Updated last sync timestamp to: {last_sync_dt.isoformat()} ({current_max_updated_at})",
                extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
            )
        elif updated_at_after is None and processed_total > 0:
            # If we didn't have a previous sync and processed articles, set timestamp to now
            now = datetime.now(tz=UTC)
            await set_tenant_config_value(last_sync_key, now.isoformat(), tenant_id)
            logger.info(
                f"Set initial last sync timestamp to: {now.isoformat()}",
                extra={"tenant_id": tenant_id, "last_sync": now.isoformat()},
            )

        logger.info(
            "Completed Intercom Help Center articles backfill",
            extra={
                "tenant_id": tenant_id,
                "processed_total": processed_total,
                "page_count": page_count,
            },
        )

    async def process_articles_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        article_ids: list[str],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
        workspace_id: str | None = None,
    ) -> None:
        """Process a batch of specific Help Center articles by ID."""
        intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id if not provided
        if workspace_id is None:
            workspace_id = await self.get_workspace_id(intercom_client)
        repo = ArtifactRepository(db_pool)
        entity_ids: list[str] = []

        logger.info(
            f"Processing batch of {len(article_ids)} Help Center articles",
            extra={"tenant_id": tenant_id, "article_count": len(article_ids)},
        )

        for article_id in article_ids:
            try:
                full_article = intercom_client.get_article(article_id)
                artifact = await self.process_article(
                    job_id, full_article, tenant_id, db_pool, workspace_id
                )

                await repo.upsert_artifact(artifact)
                entity_ids.append(artifact.entity_id)

                # Trigger indexing in batches
                if len(entity_ids) >= DEFAULT_INDEX_BATCH_SIZE:
                    await trigger_indexing(
                        entity_ids=entity_ids,
                        source=DocumentSource.INTERCOM,
                        tenant_id=tenant_id,
                        backfill_id=backfill_id,
                        suppress_notification=suppress_notification,
                    )
                    entity_ids = []

            except Exception as e:
                logger.error(
                    f"Failed to process article {article_id}: {e}",
                    extra={"tenant_id": tenant_id, "article_id": article_id},
                )
                continue

        # Trigger indexing for remaining entities
        if entity_ids:
            await trigger_indexing(
                entity_ids=entity_ids,
                source=DocumentSource.INTERCOM,
                tenant_id=tenant_id,
                backfill_id=backfill_id,
                suppress_notification=suppress_notification,
            )

    async def process_article(
        self,
        job_id: str,
        article_data: dict,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        workspace_id: str | None = None,
    ) -> IntercomHelpCenterArticleArtifact:
        """
        Process a single Help Center article and create an artifact.

        Args:
            job_id: The ingest job ID
            article_data: Raw, fresh article data from Intercom API
            tenant_id: The tenant ID
            db_pool: Database pool for token expiry management
            workspace_id: The Intercom workspace ID (app_id) for citation URLs
        """
        if not isinstance(article_data, dict):
            raise ValueError(
                f"Article data must be a dict, got {type(article_data)}: {article_data}"
            )

        article_id = article_data.get("id")
        if not article_id:
            available_keys = list(article_data.keys())[:10]
            raise ValueError(
                f"Article ID not found in article data. Available keys: {available_keys}. "
                f"Full data: {article_data}"
            )

        def _normalize_timestamp(value: Any | None) -> tuple[str, datetime]:
            """Normalize Intercom timestamp fields which may be ints or strings."""
            if isinstance(value, int):
                dt = datetime.fromtimestamp(value, tz=UTC)
                return str(value), dt
            if isinstance(value, str):
                try:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return value, dt
                except ValueError:
                    try:
                        epoch = int(value)
                        dt = datetime.fromtimestamp(epoch, tz=UTC)
                        return value, dt
                    except ValueError:
                        pass
            now = datetime.now(tz=UTC)
            return str(int(now.timestamp())), now

        title = article_data.get("title", "")
        state = article_data.get("state", "draft")

        created_at_raw = article_data.get("created_at")
        created_at_str, created_at_dt = _normalize_timestamp(created_at_raw)

        updated_at_raw = article_data.get("updated_at")
        updated_at_str, updated_at_dt = _normalize_timestamp(updated_at_raw or created_at_raw)

        # Use passed workspace_id, or try to get from article data (unlikely to be present)
        effective_workspace_id = workspace_id or article_data.get("workspace_id")

        metadata = IntercomHelpCenterArticleArtifactMetadata(
            article_id=str(article_id),
            title=str(title),
            state=str(state),
            created_at=created_at_str,
            updated_at=updated_at_str,
            workspace_id=effective_workspace_id,
        )

        # Convert raw dict to typed Pydantic model, injecting workspace_id if available
        article_data_with_workspace = {**article_data}
        if effective_workspace_id:
            article_data_with_workspace["workspace_id"] = effective_workspace_id
        typed_article_data = IntercomArticleData.model_validate(article_data_with_workspace)

        content = IntercomHelpCenterArticleArtifactContent(
            article_data=typed_article_data,
        )

        artifact = IntercomHelpCenterArticleArtifact(
            entity_id=str(article_id),
            ingest_job_id=UUID(job_id),
            content=content,
            metadata=metadata,
            source_updated_at=updated_at_dt,
        )

        return artifact
