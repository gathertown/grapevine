import logging
from datetime import datetime
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_notion_doc_id
from connectors.base.document_source import DocumentSource
from connectors.notion.notion_artifacts import (
    NotionPageArtifact,
    NotionUserArtifact,
)
from connectors.notion.notion_models import (
    NotionBlockData,
    NotionCommentData,
    NotionPageDocumentData,
)
from connectors.notion.notion_page_document import NotionPageDocument
from connectors.notion.notion_parent_utils import extract_parent_info
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class NotionTransformer(BaseTransformer[NotionPageDocument]):
    def __init__(self):
        super().__init__(DocumentSource.NOTION)
        self.user_artifacts: list[NotionUserArtifact] = []

    def _get_user_name(self, user_id: str) -> str:
        for user_artifact in self.user_artifacts:
            if user_artifact.content.id == user_id:
                return user_artifact.content.name or user_id
        return user_id

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[NotionPageDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        # Refresh all Notion user artifacts, since we may need them to generate documents
        self.user_artifacts = await repo.get_artifacts(NotionUserArtifact)
        logger.info(f"Loaded {len(self.user_artifacts)} users")

        page_artifacts = await repo.get_artifacts_by_entity_ids(NotionPageArtifact, entity_ids)
        logger.info(f"Loaded {len(page_artifacts)} page artifacts for {len(entity_ids)} entity IDs")

        documents = []
        counter: ErrorCounter = {}

        for artifact in page_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)

                    if len(documents) % 100 == 0:
                        logger.info(f"Processed {len(documents)}/{len(page_artifacts)} pages")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Notion transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(page_artifacts)} artifacts"
        )
        return documents

    async def _create_document(self, artifact: NotionPageArtifact) -> NotionPageDocument:
        try:
            page_id = artifact.metadata.page_id

            processed_blocks = self._process_blocks(
                artifact.content.blocks,
                page_id,
                artifact.metadata.model_dump(),
            )

            processed_comments = self._process_comments(artifact.content.comments)

            document_data = NotionPageDocumentData(
                page_id=page_id,
                page_title=artifact.metadata.page_title,
                page_url=artifact.content.page_data.get("url", ""),
                database_id=artifact.metadata.database_id,
                workspace_id=artifact.metadata.workspace_id,
                properties=self._extract_properties(
                    artifact.content.page_data.get("properties", {})
                ),
                blocks=[NotionBlockData(**block) for block in processed_blocks],
                comments=processed_comments,
                page_created_time=artifact.content.page_data.get("created_time"),
                created_time=artifact.content.page_data.get("created_time"),
                last_edited_time=artifact.content.page_data.get("last_edited_time"),
            )

            document_id = get_notion_doc_id(page_id)

            return NotionPageDocument(
                id=document_id,
                raw_data=document_data.model_dump(),
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

        except Exception as e:
            logger.error(f"Failed to create document for page {artifact.metadata.page_id}: {e}")
            return None  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    def _extract_properties(self, properties: dict[str, Any]) -> dict[str, str]:
        extracted = {}

        for prop_name, prop_data in properties.items():
            # opensearch throws up on empty-string property names
            if prop_name == "":
                prop_name = "[Empty property name]"
            prop_type = prop_data.get("type")

            if prop_type == "title":
                continue
            elif prop_type == "rich_text":
                text = self._extract_rich_text(prop_data.get("rich_text", []))
                if text:
                    extracted[prop_name] = text
            elif prop_type == "number":
                number = prop_data.get("number")
                if number is not None:
                    extracted[prop_name] = str(number)
            elif prop_type == "select":
                select = prop_data.get("select")
                if select:
                    extracted[prop_name] = select.get("name", "")
            elif prop_type == "multi_select":
                multi_select = prop_data.get("multi_select", [])
                if multi_select:
                    names = [item.get("name", "") for item in multi_select]
                    extracted[prop_name] = ", ".join(names)
            elif prop_type == "date":
                date_obj = prop_data.get("date")
                if date_obj:
                    start = date_obj.get("start", "")
                    end = date_obj.get("end", "")
                    if end:
                        extracted[prop_name] = f"{start} to {end}"
                    else:
                        extracted[prop_name] = start
            elif prop_type == "checkbox":
                checkbox = prop_data.get("checkbox", False)
                extracted[prop_name] = "Yes" if checkbox else "No"
            elif prop_type == "url":
                url = prop_data.get("url")
                if url:
                    extracted[prop_name] = url
            elif prop_type == "email":
                email = prop_data.get("email")
                if email:
                    extracted[prop_name] = email
            elif prop_type == "phone_number":
                phone = prop_data.get("phone_number")
                if phone:
                    extracted[prop_name] = phone
            elif prop_type == "status":
                status = prop_data.get("status")
                if status:
                    extracted[prop_name] = status.get("name", "")

        return extracted

    def _process_blocks(
        self,
        blocks_data: list[dict[str, Any]],
        page_id: str,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        blocks = []

        for block_data in blocks_data:
            block_id = block_data.get("id", "")
            block_type = block_data.get("type", "")

            if not block_type or not block_id:
                continue

            block_content_data = block_data.get(block_type, {})
            content = self._extract_block_content(block_type, block_content_data, block_id)

            if content.strip():
                last_edited_by_id = block_data.get("last_edited_by", {}).get("id", "")
                last_edited_by_name = self._get_user_name(last_edited_by_id)

                block_info = {
                    "block_type": block_type,
                    "block_id": block_id,
                    "content": content,
                    "timestamp": block_data.get("last_edited_time", ""),
                    "formatted_time": self._format_timestamp(
                        block_data.get("last_edited_time", "")
                    ),
                    "page_id": page_id,
                    "page_title": metadata.get("page_title", "Untitled"),
                    "database_id": metadata.get("database_id"),
                    "workspace_id": metadata.get("workspace_id"),
                    "language": "",
                    "checked": None,
                    "list_number": None,
                    "nesting_level": block_data.get("nesting_level", 0),
                    "last_edited_by": last_edited_by_id,
                    "last_edited_by_name": last_edited_by_name,
                }

                if block_type == "code":
                    block_info["language"] = block_content_data.get("language", "")
                elif block_type == "to_do":
                    block_info["checked"] = block_content_data.get("checked", False)
                elif block_type in ["numbered_list_item"]:
                    block_info["list_number"] = 1

                blocks.append(block_info)

        return blocks

    def _process_comments(self, comments_data: list[dict[str, Any]]) -> list[NotionCommentData]:
        """Process comments into structured format for search."""
        comments = []

        for comment_data in comments_data:
            comment_id = comment_data.get("id", "")
            if not comment_id:
                continue

            rich_text = comment_data.get("rich_text", [])
            content = self._extract_rich_text(rich_text)

            if not content.strip():
                continue

            created_by_id = comment_data.get("created_by", {}).get("id", "")
            created_by_name = self._get_user_name(created_by_id)

            parent = comment_data.get("parent", {})
            parent_info = extract_parent_info(parent, comment_id)

            comment_info = NotionCommentData(
                comment_id=comment_id,
                content=content,
                created_time=comment_data.get("created_time"),
                last_edited_time=comment_data.get("last_edited_time"),
                created_by=created_by_id,
                created_by_name=created_by_name,
                parent_id=parent_info.parent_id,
                parent_type=parent_info.parent_type,
            )

            comments.append(comment_info)

        return comments

    def _extract_block_content(
        self, block_type: str, block_data: dict[str, Any], block_id: str | None = None
    ) -> str:
        if "rich_text" in block_data:
            return self._extract_rich_text(block_data.get("rich_text", []))
        elif block_type == "image":
            caption = self._extract_rich_text(block_data.get("caption", []))
            return f"[Image: {caption}]" if caption else "[Image]"
        elif block_type == "file":
            name = block_data.get("name", "File")
            return f"[File: {name}]"
        elif block_type == "video":
            caption = self._extract_rich_text(block_data.get("caption", []))
            return f"[Video: {caption}]" if caption else "[Video]"
        elif block_type == "audio":
            caption = self._extract_rich_text(block_data.get("caption", []))
            return f"[Audio: {caption}]" if caption else "[Audio]"
        elif block_type == "embed":
            url = block_data.get("url", "")
            return f"[Embed: {url}]" if url else "[Embed]"
        elif block_type == "bookmark":
            url = block_data.get("url", "")
            caption = self._extract_rich_text(block_data.get("caption", []))
            return f"[Bookmark: {caption or url}]"
        elif block_type == "divider":
            return "---"
        elif block_type == "table":
            return "[Table]"
        elif block_type == "child_page":
            title = block_data.get("title", "Untitled")
            # Child pages in blocks have their ID in the parent block's ID
            if block_id:
                # Convert block ID to URL format (remove hyphens)
                page_id_for_url = block_id.replace("-", "")
                return f"[Child Page: {title}](https://www.notion.so/{page_id_for_url})"
            return f"[Child Page: {title}]"
        elif block_type == "child_database":
            title = block_data.get("title", "Untitled")
            return f"[Child Database: {title}]"
        else:
            return ""

    def _extract_rich_text(self, rich_text_array: list[dict[str, Any]]) -> str:
        text_parts = []
        for text_obj in rich_text_array:
            obj_type = text_obj.get("type")

            if obj_type == "text":
                text_parts.append(text_obj.get("text", {}).get("content", ""))
            elif obj_type == "mention":
                mention_data = text_obj.get("mention", {})
                mention_type = mention_data.get("type")

                if mention_type == "link_preview":
                    url = mention_data.get("link_preview", {}).get("url", "")
                    text_parts.append(url)
                elif mention_type == "page":
                    # Format page mentions as markdown links
                    text_parts.append(
                        f"[{text_obj.get('plain_text', '')}]({text_obj.get('href', '')})"
                    )
                elif mention_type == "database":
                    text_parts.append(f"[Database Mention: {text_obj.get('plain_text', '')}]")
                else:
                    # Other mention types: database, user, date, etc
                    text_parts.append(text_obj.get("plain_text", ""))
            elif obj_type == "equation":
                text_parts.append(text_obj.get("equation", {}).get("expression", ""))
            else:
                plain_text = text_obj.get("plain_text", "")
                if plain_text:
                    text_parts.append(plain_text)

        return "".join(text_parts)

    def _format_timestamp(self, timestamp: str) -> str:
        if not timestamp:
            return ""

        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Failed to format timestamp {timestamp}: {e}")
            return timestamp
