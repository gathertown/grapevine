import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.zendesk.extractors.zendesk_artifacts import (
    ZendeskArticleArtifact,
    ZendeskCategoryArtifact,
    ZendeskCommentArtifact,
    ZendeskSectionArtifact,
    ZendeskUserArtifact,
    zendesk_category_entity_id,
    zendesk_section_entity_id,
    zendesk_user_entity_id,
)
from connectors.zendesk.transformers.zendesk_article_document import ZendeskArticleDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ZendeskArticleTransformer(BaseTransformer[ZendeskArticleDocument]):
    def __init__(self):
        super().__init__(DocumentSource.ZENDESK_ARTICLE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[ZendeskArticleDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        article_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskArticleArtifact, entity_ids
        )

        logger.info(
            f"Loaded {len(article_artifacts)} Zendesk article artifacts for {len(entity_ids)} entity IDs"
        )

        section_by_id = await self._get_section_artifacts_by_id(repo, article_artifacts)
        all_section_artifacts = list(section_by_id.values())
        category_by_id = await self._get_category_artifacts_by_id(repo, all_section_artifacts)

        comments_by_source_id = await self._get_comments_artifacts_by_source_id(
            repo, article_artifacts
        )

        all_comment_artifacts = [
            comment
            for article_comments in comments_by_source_id.values()
            for comment in article_comments
        ]
        user_by_id = await self._get_user_artifacts_by_id(
            repo, article_artifacts, all_comment_artifacts
        )

        documents: list[ZendeskArticleDocument] = []
        for artifact in article_artifacts:
            section_artifact = section_by_id.get(artifact.content.section_id)
            category_artifact = (
                category_by_id.get(section_artifact.content.category_id)
                if section_artifact
                else None
            )

            documents.append(
                ZendeskArticleDocument.from_artifacts(
                    article_artifact=artifact,
                    comment_artifacts=comments_by_source_id.get(artifact.content.id, []),
                    # passing in all users by ID because its easy, should really only pass in the required ones
                    user_artifacts=user_by_id,
                    section_artifact=section_artifact,
                    category_artifact=category_artifact,
                )
            )

        logger.info(
            f"Zendesk Article transformation complete: Created {len(documents)} documents from {len(entity_ids)} entity_ids and {len(article_artifacts)} article artifacts."
        )

        return documents

    async def _get_user_artifacts_by_id(
        self,
        repo: ArtifactRepository,
        article_artifacts: list[ZendeskArticleArtifact],
        comment_artifacts: list[ZendeskCommentArtifact],
    ) -> dict[int, ZendeskUserArtifact]:
        article_user_ids = {article.content.author_id for article in article_artifacts}
        comment_user_ids = {comment.content.author_id for comment in comment_artifacts}
        all_user_ids = article_user_ids | comment_user_ids

        user_entity_ids = [zendesk_user_entity_id(user_id) for user_id in all_user_ids]

        user_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskUserArtifact, user_entity_ids
        )

        return {user.content.id: user for user in user_artifacts}

    async def _get_section_artifacts_by_id(
        self, repo: ArtifactRepository, article_artifacts: list[ZendeskArticleArtifact]
    ) -> dict[int, ZendeskSectionArtifact]:
        section_ids = {article.content.section_id for article in article_artifacts}
        section_entity_ids = [zendesk_section_entity_id(section_id) for section_id in section_ids]

        section_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskSectionArtifact, section_entity_ids
        )

        return {section.content.id: section for section in section_artifacts}

    async def _get_category_artifacts_by_id(
        self, repo: ArtifactRepository, section_artifacts: list[ZendeskSectionArtifact]
    ) -> dict[int, ZendeskCategoryArtifact]:
        category_ids = {section.content.category_id for section in section_artifacts}
        category_entity_ids = [
            zendesk_category_entity_id(category_id) for category_id in category_ids
        ]
        category_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskCategoryArtifact, category_entity_ids
        )

        return {category.content.id: category for category in category_artifacts}

    async def _get_comments_artifacts_by_source_id(
        self, repo: ArtifactRepository, article_artifacts: list[ZendeskArticleArtifact]
    ) -> dict[int, list[ZendeskCommentArtifact]]:
        article_ids = {str(article.content.id) for article in article_artifacts}
        comment_artifacts = await repo.get_artifacts_by_metadata_filter(
            ZendeskCommentArtifact, batches={"source_id": list(article_ids)}
        )

        comments_by_source_id: dict[int, list[ZendeskCommentArtifact]] = {}
        for comment in comment_artifacts:
            comments_by_source_id.setdefault(comment.content.source_id, []).append(comment)

        return comments_by_source_id
