"""Transformer for Trello card artifacts to TrelloCardDocuments."""

import logging
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.trello.trello_artifacts import TrelloCardArtifact
from connectors.trello.trello_card_document import TrelloCardDocument
from src.ingest.repositories import ArtifactRepository
from src.permissions.models import PermissionPolicy
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class TrelloTransformer(BaseTransformer[TrelloCardDocument]):
    """Transform Trello card artifacts into TrelloCardDocuments."""

    def __init__(self):
        super().__init__(DocumentSource.TRELLO)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[TrelloCardDocument]:
        """Transform Trello card artifacts into TrelloCardDocuments.

        Args:
            entity_ids: List of card entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of TrelloCardDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)
        card_artifacts = await repo.get_artifacts_by_entity_ids(TrelloCardArtifact, entity_ids)

        logger.info(
            f"Loaded {len(card_artifacts)} Trello card artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for artifact in card_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)

                    if len(documents) % 100 == 0:
                        logger.info(
                            f"Processed {len(documents)}/{len(card_artifacts)} Trello cards"
                        )
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Trello transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(card_artifacts)} artifacts"
        )
        return documents

    async def _create_document(
        self,
        artifact: TrelloCardArtifact,
    ) -> TrelloCardDocument | None:
        """Create a TrelloCardDocument from a card artifact.

        All necessary data (board name, list name, member info) is already resolved
        in the artifact metadata and content from the Trello API response.

        Args:
            artifact: TrelloCardArtifact instance

        Returns:
            TrelloCardDocument or None if creation fails
        """
        try:
            metadata = artifact.metadata
            content = artifact.content

            board_name = metadata.board_name or "Unknown Board"
            list_name = metadata.list_name or "Unknown List"

            assigned_members = []
            card_data = content.card_data
            for member in card_data.get("members", []):
                member_id = member.get("id", "")
                username = member.get("username") or member.get("fullName", "")
                if username:
                    assigned_members.append(f"<@{member_id}|@{username}>")

            assigned_members_text = ", ".join(assigned_members) if assigned_members else ""

            label_names = []
            for label in metadata.labels:
                label_name = label.get("name", "").strip()
                label_color = label.get("color", "")
                if label_name:
                    label_names.append(label_name)
                elif label_color:
                    label_names.append(f"[{label_color}]")
            labels_text = ", ".join(label_names) if label_names else ""

            comments = []
            for comment_action in content.comments:
                member_creator = comment_action.get("memberCreator", {})
                member_id = member_creator.get("id", "")
                username = member_creator.get("username", "Unknown")
                date = comment_action.get("date", "")
                comment_text = comment_action.get("data", {}).get("text", "")

                if not comment_text:
                    continue

                formatted_content = f"{date} <@{member_id}|@{username}> commented: {comment_text}"

                comments.append(
                    {
                        "content": formatted_content,
                        "comment_id": comment_action.get("id"),
                        "comment_author": username,
                        "timestamp": date,
                    }
                )

            # Format checklists from card content
            checklists = []
            for checklist in content.checklists:
                checklist_name = checklist.get("name", "Checklist")
                check_items = checklist.get("checkItems", [])

                if not check_items:
                    continue

                checklist_parts = [f"Checklist: {checklist_name}"]
                for item in check_items:
                    item_name = item.get("name", "")
                    state = item.get("state", "incomplete")
                    status = "✓" if state == "complete" else "☐"
                    checklist_parts.append(f"{status} {item_name}")

                checklists.append(
                    {
                        "content": "\n".join(checklist_parts),
                        "checklist_id": checklist.get("id"),
                        "checklist_name": checklist_name,
                    }
                )

            # Format significant actions (we can query these separately or include in card data)
            # For now, skip actions as they're typically fetched separately via the actions endpoint
            actions: list[dict[str, Any]] = []

            # Format attachments from card data
            attachments: list[dict[str, Any]] = []
            for attachment in card_data.get("attachments", []):
                attachment_name = attachment.get("name", "")
                attachment_url = attachment.get("url", "")

                if not attachment_name:
                    continue

                attachments.append(
                    {
                        "content": f"Attachment: {attachment_name}\nURL: {attachment_url}",
                        "attachment_id": attachment.get("id"),
                        "attachment_name": attachment_name,
                    }
                )

            # Build document data
            document_data = {
                "card_id": metadata.card_id,
                "card_name": metadata.card_name,
                "card_desc": metadata.desc or "",
                "board_id": metadata.id_board,
                "board_name": board_name,
                "list_id": metadata.id_list,
                "list_name": list_name,
                "url": metadata.url,
                "assigned_members_text": assigned_members_text,
                "labels_text": labels_text,
                "due_date": metadata.due,
                "due_complete": metadata.due_complete,
                "closed": metadata.closed,
                "comments": comments,
                "checklists": checklists,
                "actions": actions,
                "attachments": attachments,
                "source_created_at": artifact.source_updated_at.isoformat(),
            }

            # Determine permission policy based on board visibility
            permission_policy: PermissionPolicy = "tenant"
            permission_allowed_tokens: list[str] | None = None

            board_permission_level = metadata.board_permission_level
            if board_permission_level == "private":
                # Private boards - only board members can see
                permission_policy = "private"
                board_member_emails = metadata.board_member_emails
                if board_member_emails:
                    permission_allowed_tokens = [f"e:{email}" for email in board_member_emails]
                    logger.debug(
                        f"Set private permissions for card {metadata.card_id} with {len(permission_allowed_tokens)} members"
                    )
                else:
                    logger.warning(
                        f"Card {metadata.card_id} is on private board but has no member emails"
                    )
            else:
                # "org" or "public" boards - visible to entire tenant
                logger.debug(
                    f"Set tenant permissions for card {metadata.card_id} (board permission: {board_permission_level})"
                )

            document = TrelloCardDocument(
                id=f"trello_card_{metadata.card_id}",
                raw_data=document_data,
                source_updated_at=artifact.source_updated_at,
                permission_policy=permission_policy,
                permission_allowed_tokens=permission_allowed_tokens,
            )

            return document

        except Exception as e:
            logger.error(f"Failed to create document for Trello card {artifact.entity_id}: {e}")
            return None
