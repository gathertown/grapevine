"""Trello card document and chunk models for search."""

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class TrelloCardChunkMetadata(TypedDict):
    """Metadata for Trello card chunks."""

    activity_type: str | None  # "header", "comment", "checklist", "action", "attachment"
    card_id: str | None
    card_name: str | None
    board_id: str | None
    board_name: str | None
    list_id: str | None
    list_name: str | None
    # Type-specific fields (only present for certain activity types)
    comment_id: NotRequired[str | None]
    comment_author: NotRequired[str | None]
    timestamp: NotRequired[str | None]
    checklist_id: NotRequired[str | None]
    checklist_name: NotRequired[str | None]
    action_id: NotRequired[str | None]
    action_type: NotRequired[str | None]
    attachment_id: NotRequired[str | None]
    attachment_name: NotRequired[str | None]


class TrelloCardDocumentMetadata(TypedDict):
    """Metadata for Trello card documents."""

    card_id: str
    card_name: str
    board_id: str
    board_name: str
    list_id: str
    list_name: str
    url: str | None
    source_created_at: str | None
    assigned_members_text: str
    labels_text: str


@dataclass
class TrelloCardChunk(BaseChunk[TrelloCardChunkMetadata]):
    """Chunk of a Trello card for embedding and search."""

    def get_content(self) -> str:
        """Return the content to be embedded."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> TrelloCardChunkMetadata:
        """Return metadata for this chunk."""
        return self.raw_data  # type: ignore


@dataclass
class TrelloCardDocument(BaseDocument[TrelloCardChunk, TrelloCardDocumentMetadata]):
    """Document representing a Trello card with all its content."""

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Get document content by combining all chunks."""
        return "\n".join(chunk.get_content() for chunk in self.to_embedding_chunks())

    def get_metadata(self) -> TrelloCardDocumentMetadata:
        """Get document metadata."""
        return {
            "card_id": self.raw_data.get("card_id", ""),
            "card_name": self.raw_data.get("card_name", ""),
            "board_id": self.raw_data.get("board_id", ""),
            "board_name": self.raw_data.get("board_name", ""),
            "list_id": self.raw_data.get("list_id", ""),
            "list_name": self.raw_data.get("list_name", ""),
            "url": self.raw_data.get("url"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "assigned_members_text": self.raw_data.get("assigned_members_text", ""),
            "labels_text": self.raw_data.get("labels_text", ""),
        }

    def get_source_enum(self) -> DocumentSource:
        """Get document source enum."""
        return DocumentSource.TRELLO

    def to_embedding_chunks(self) -> list[TrelloCardChunk]:
        """Split document into chunks for embedding.

        Chunking strategy:
        1. Header chunk: Card overview with description and key metadata
        2. One chunk per comment (significant discussions)
        3. One chunk per checklist (task lists and progress)
        4. One chunk per significant action (moves, member adds)
        5. One chunk per attachment (file references)
        """
        chunks: list[TrelloCardChunk] = []

        # 1. Header chunk - card overview
        header_data = dict(self.raw_data)
        header_data["activity_type"] = "header"
        header_data["content"] = self._get_header_content()
        chunks.append(TrelloCardChunk(document=self, raw_data=header_data))

        # 2. Comment chunks
        for idx, comment in enumerate(self.raw_data.get("comments", [])):
            comment_data = dict(self.raw_data)
            comment_data.update(comment)
            comment_data["activity_type"] = "comment"

            # Add "Comments:" header before the first comment's content
            if idx == 0 and "content" in comment_data:
                comment_data["content"] = f"\nComments:\n{comment_data['content']}"

            chunks.append(TrelloCardChunk(document=self, raw_data=comment_data))

        # 3. Checklist chunks
        for idx, checklist in enumerate(self.raw_data.get("checklists", [])):
            checklist_data = dict(self.raw_data)
            checklist_data.update(checklist)
            checklist_data["activity_type"] = "checklist"

            # Add "Checklists:" header before the first checklist's content
            if idx == 0 and "content" in checklist_data:
                checklist_data["content"] = f"\nChecklists:\n{checklist_data['content']}"

            chunks.append(TrelloCardChunk(document=self, raw_data=checklist_data))

        # 4. Significant action chunks
        for idx, action in enumerate(self.raw_data.get("actions", [])):
            action_data = dict(self.raw_data)
            action_data.update(action)
            action_data["activity_type"] = "action"

            # Add "Actions:" header before the first action's content
            if idx == 0 and "content" in action_data:
                action_data["content"] = f"\nActions:\n{action_data['content']}"

            chunks.append(TrelloCardChunk(document=self, raw_data=action_data))

        # 5. Attachment chunks
        for idx, attachment in enumerate(self.raw_data.get("attachments", [])):
            attachment_data = dict(self.raw_data)
            attachment_data.update(attachment)
            attachment_data["activity_type"] = "attachment"

            # Add "Attachments:" header before the first attachment's content
            if idx == 0 and "content" in attachment_data:
                attachment_data["content"] = f"\nAttachments:\n{attachment_data['content']}"

            chunks.append(TrelloCardChunk(document=self, raw_data=attachment_data))

        return chunks

    def _get_header_content(self) -> str:
        """Generate header content for the card."""
        card_name = self.raw_data.get("card_name", "")
        card_desc = self.raw_data.get("card_desc", "")
        board_name = self.raw_data.get("board_name", "")
        list_name = self.raw_data.get("list_name", "")
        url = self.raw_data.get("url", "")
        assigned_members_text = self.raw_data.get("assigned_members_text", "")
        labels_text = self.raw_data.get("labels_text", "")
        due_date = self.raw_data.get("due_date")
        due_complete = self.raw_data.get("due_complete", False)

        header_lines = [
            f"Card: {card_name}",
            f"Board: {board_name}",
            f"List: {list_name}",
        ]

        if url:
            header_lines.append(f"URL: {url}")

        if assigned_members_text:
            header_lines.append(f"Members: {assigned_members_text}")

        if labels_text:
            header_lines.append(f"Labels: {labels_text}")

        if due_date:
            due_status = " (Complete)" if due_complete else ""
            header_lines.append(f"Due: {due_date}{due_status}")

        if card_desc:
            header_lines.extend(["", "Description:", card_desc])

        return "\n".join(header_lines)
