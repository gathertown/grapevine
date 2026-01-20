"""Unit tests for the TrelloTransformer."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from connectors.trello import (
    TrelloCardArtifact,
    TrelloCardArtifactContent,
    TrelloCardArtifactMetadata,
    TrelloCardDocument,
    TrelloTransformer,
)


@pytest.fixture
def transformer() -> TrelloTransformer:
    """Create a TrelloTransformer instance."""
    return TrelloTransformer()


@pytest.fixture
def base_card_data() -> dict:
    """Create base Trello card data from API."""
    return {
        "id": "card-123",
        "name": "Test Card",
        "desc": "Test card description",
        "idList": "list-456",
        "idBoard": "board-789",
        "idMembers": ["member-1", "member-2"],
        "idLabels": ["label-1"],
        "closed": False,
        "due": "2024-01-15T10:00:00.000Z",
        "dueComplete": False,
        "start": None,
        "pos": 16384.0,
        "shortUrl": "https://trello.com/c/abc123",
        "url": "https://trello.com/c/abc123/test-card",
        "dateLastActivity": "2024-01-15T10:00:00.000Z",
        "idShort": 42,
        "subscribed": True,
        "members": [
            {
                "id": "member-1",
                "username": "alice",
                "fullName": "Alice Smith",
            },
            {
                "id": "member-2",
                "username": "bob",
                "fullName": "Bob Jones",
            },
        ],
        "attachments": [
            {
                "id": "attachment-1",
                "name": "design.pdf",
                "url": "https://trello.com/attachments/design.pdf",
            }
        ],
    }


@pytest.fixture
def comments_data() -> list[dict]:
    """Create comment actions data."""
    return [
        {
            "id": "comment-1",
            "type": "commentCard",
            "date": "2024-01-15T11:00:00.000Z",
            "memberCreator": {
                "id": "member-1",
                "username": "alice",
                "fullName": "Alice Smith",
            },
            "data": {
                "text": "This looks good!",
            },
        },
        {
            "id": "comment-2",
            "type": "commentCard",
            "date": "2024-01-15T12:00:00.000Z",
            "memberCreator": {
                "id": "member-2",
                "username": "bob",
                "fullName": "Bob Jones",
            },
            "data": {
                "text": "Approved",
            },
        },
    ]


@pytest.fixture
def checklists_data() -> list[dict]:
    """Create checklist data."""
    return [
        {
            "id": "checklist-1",
            "name": "Tasks",
            "checkItems": [
                {
                    "id": "item-1",
                    "name": "Review code",
                    "state": "complete",
                },
                {
                    "id": "item-2",
                    "name": "Update docs",
                    "state": "incomplete",
                },
            ],
        }
    ]


@pytest.fixture
def private_board_artifact(
    base_card_data: dict, comments_data: list[dict], checklists_data: list[dict]
) -> TrelloCardArtifact:
    """Create a card artifact from a private board."""
    return TrelloCardArtifact(
        entity_id="card-123",
        ingest_job_id=uuid4(),
        content=TrelloCardArtifactContent(
            card_data=base_card_data,
            comments=comments_data,
            checklists=checklists_data,
        ),
        metadata=TrelloCardArtifactMetadata(
            card_id="card-123",
            card_name="Test Card",
            desc="Test card description",
            id_list="list-456",
            list_name="To Do",
            id_board="board-789",
            board_name="Private Board",
            id_members=["member-1", "member-2"],
            labels=[
                {"id": "label-1", "name": "Priority", "color": "red"},
            ],
            closed=False,
            due="2024-01-15T10:00:00.000Z",
            due_complete=False,
            start=None,
            pos=16384.0,
            short_url="https://trello.com/c/abc123",
            url="https://trello.com/c/abc123/test-card",
            date_last_activity="2024-01-15T10:00:00.000Z",
            id_short=42,
            subscribed=True,
            board_permission_level="private",
            board_member_emails=["alice@company.com", "bob@company.com"],
        ),
        source_updated_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def org_board_artifact(
    base_card_data: dict, comments_data: list[dict], checklists_data: list[dict]
) -> TrelloCardArtifact:
    """Create a card artifact from an org board."""
    return TrelloCardArtifact(
        entity_id="card-456",
        ingest_job_id=uuid4(),
        content=TrelloCardArtifactContent(
            card_data=base_card_data,
            comments=comments_data,
            checklists=checklists_data,
        ),
        metadata=TrelloCardArtifactMetadata(
            card_id="card-456",
            card_name="Org Card",
            desc="Organization card",
            id_list="list-789",
            list_name="In Progress",
            id_board="board-org",
            board_name="Organization Board",
            id_members=[],
            labels=[],
            closed=False,
            due=None,
            due_complete=False,
            start=None,
            pos=32768.0,
            short_url="https://trello.com/c/def456",
            url="https://trello.com/c/def456/org-card",
            date_last_activity="2024-01-15T10:00:00.000Z",
            id_short=43,
            subscribed=False,
            board_permission_level="org",
            board_member_emails=["alice@company.com", "bob@company.com", "carol@company.com"],
        ),
        source_updated_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def public_board_artifact(
    base_card_data: dict, comments_data: list[dict], checklists_data: list[dict]
) -> TrelloCardArtifact:
    """Create a card artifact from a public board."""
    return TrelloCardArtifact(
        entity_id="card-789",
        ingest_job_id=uuid4(),
        content=TrelloCardArtifactContent(
            card_data=base_card_data,
            comments=comments_data,
            checklists=checklists_data,
        ),
        metadata=TrelloCardArtifactMetadata(
            card_id="card-789",
            card_name="Public Card",
            desc="Public card",
            id_list="list-public",
            list_name="Done",
            id_board="board-public",
            board_name="Public Board",
            id_members=[],
            labels=[],
            closed=False,
            due=None,
            due_complete=False,
            start=None,
            pos=49152.0,
            short_url="https://trello.com/c/ghi789",
            url="https://trello.com/c/ghi789/public-card",
            date_last_activity="2024-01-15T10:00:00.000Z",
            id_short=44,
            subscribed=False,
            board_permission_level="public",
            board_member_emails=[],
        ),
        source_updated_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


class TestTrelloPermissions:
    """Test permission handling in Trello transformer."""

    async def test_private_board_sets_private_permission_policy(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that private boards get private permission policy with email tokens."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert isinstance(document, TrelloCardDocument)
        assert document.permission_policy == "private"
        assert document.permission_allowed_tokens is not None
        assert len(document.permission_allowed_tokens) == 2
        assert "e:alice@company.com" in document.permission_allowed_tokens
        assert "e:bob@company.com" in document.permission_allowed_tokens

    async def test_org_board_sets_tenant_permission_policy(
        self, transformer: TrelloTransformer, org_board_artifact: TrelloCardArtifact
    ):
        """Test that org boards get tenant permission policy."""
        document = await transformer._create_document(org_board_artifact)

        assert document is not None
        assert isinstance(document, TrelloCardDocument)
        assert document.permission_policy == "tenant"
        assert document.permission_allowed_tokens is None

    async def test_public_board_sets_tenant_permission_policy(
        self, transformer: TrelloTransformer, public_board_artifact: TrelloCardArtifact
    ):
        """Test that public boards get tenant permission policy."""
        document = await transformer._create_document(public_board_artifact)

        assert document is not None
        assert isinstance(document, TrelloCardDocument)
        assert document.permission_policy == "tenant"
        assert document.permission_allowed_tokens is None

    async def test_private_board_without_member_emails_logs_warning(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that private boards without member emails still get private policy but with None tokens."""
        # Remove board member emails
        private_board_artifact.metadata.board_member_emails = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.permission_policy == "private"
        # When no emails, permission_allowed_tokens is None (logged as warning)
        assert document.permission_allowed_tokens is None


class TestTrelloCardDataExtraction:
    """Test card data extraction and document creation."""

    async def test_extracts_board_and_list_names(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that board_name and list_name are properly extracted."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["board_name"] == "Private Board"
        assert document.raw_data["list_name"] == "To Do"

    async def test_extracts_basic_card_info(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that basic card information is extracted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["card_id"] == "card-123"
        assert document.raw_data["card_name"] == "Test Card"
        assert document.raw_data["card_desc"] == "Test card description"
        assert document.raw_data["board_id"] == "board-789"
        assert document.raw_data["list_id"] == "list-456"
        assert document.raw_data["url"] == "https://trello.com/c/abc123/test-card"

    async def test_extracts_assigned_members(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that assigned members are formatted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assigned_members_text = document.raw_data["assigned_members_text"]
        assert "<@member-1|@alice>" in assigned_members_text
        assert "<@member-2|@bob>" in assigned_members_text

    async def test_extracts_labels(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that labels are extracted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["labels_text"] == "Priority"

    async def test_extracts_due_date_info(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that due date information is extracted."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["due_date"] == "2024-01-15T10:00:00.000Z"
        assert document.raw_data["due_complete"] is False

    async def test_extracts_closed_status(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that closed status is extracted."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["closed"] is False

    async def test_extracts_comments(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that comments are extracted and formatted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        comments = document.raw_data["comments"]
        assert len(comments) == 2

        # Check first comment
        assert comments[0]["comment_id"] == "comment-1"
        assert comments[0]["comment_author"] == "alice"
        assert "This looks good!" in comments[0]["content"]
        assert "<@member-1|@alice>" in comments[0]["content"]

        # Check second comment
        assert comments[1]["comment_id"] == "comment-2"
        assert comments[1]["comment_author"] == "bob"
        assert "Approved" in comments[1]["content"]

    async def test_extracts_checklists(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that checklists are extracted and formatted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        checklists = document.raw_data["checklists"]
        assert len(checklists) == 1

        checklist = checklists[0]
        assert checklist["checklist_id"] == "checklist-1"
        assert checklist["checklist_name"] == "Tasks"
        assert "Checklist: Tasks" in checklist["content"]
        assert "✓ Review code" in checklist["content"]
        assert "☐ Update docs" in checklist["content"]

    async def test_extracts_attachments(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that attachments are extracted correctly."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        attachments = document.raw_data["attachments"]
        assert len(attachments) == 1

        attachment = attachments[0]
        assert attachment["attachment_id"] == "attachment-1"
        assert attachment["attachment_name"] == "design.pdf"
        assert "Attachment: design.pdf" in attachment["content"]
        assert "https://trello.com/attachments/design.pdf" in attachment["content"]

    async def test_extracts_source_created_at(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that source_created_at timestamp is extracted."""
        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["source_created_at"] == "2024-01-15T10:00:00+00:00"


class TestTrelloCardEdgeCases:
    """Test edge cases and error handling."""

    async def test_handles_missing_board_name(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test graceful handling when board_name is None."""
        private_board_artifact.metadata.board_name = None

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["board_name"] == "Unknown Board"

    async def test_handles_missing_list_name(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test graceful handling when list_name is None."""
        private_board_artifact.metadata.list_name = None

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["list_name"] == "Unknown List"

    async def test_handles_empty_description(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with empty descriptions."""
        private_board_artifact.metadata.desc = None

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["card_desc"] == ""

    async def test_handles_no_assigned_members(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with no assigned members."""
        private_board_artifact.content.card_data["members"] = []
        private_board_artifact.metadata.id_members = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["assigned_members_text"] == ""

    async def test_handles_no_labels(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with no labels."""
        private_board_artifact.metadata.labels = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert document.raw_data["labels_text"] == ""

    async def test_handles_labels_without_names(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of labels without names falls back to color."""
        private_board_artifact.metadata.labels = [
            {"id": "label-1", "name": "", "color": "green"},
            {"id": "label-2", "name": "Bug", "color": "red"},
            {"id": "label-3", "name": "", "color": "blue"},
        ]

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        # Should show color for empty names, and name when available
        assert document.raw_data["labels_text"] == "[green], Bug, [blue]"

    async def test_handles_empty_comments(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with no comments."""
        private_board_artifact.content.comments = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert len(document.raw_data["comments"]) == 0

    async def test_handles_empty_checklists(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with no checklists."""
        private_board_artifact.content.checklists = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert len(document.raw_data["checklists"]) == 0

    async def test_handles_empty_attachments(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test handling of cards with no attachments."""
        private_board_artifact.content.card_data["attachments"] = []

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        assert len(document.raw_data["attachments"]) == 0

    async def test_skips_comments_with_empty_text(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that comments with empty text are skipped."""
        private_board_artifact.content.comments.append(
            {
                "id": "comment-3",
                "type": "commentCard",
                "date": "2024-01-15T13:00:00.000Z",
                "memberCreator": {
                    "id": "member-3",
                    "username": "charlie",
                },
                "data": {
                    "text": "",  # Empty text
                },
            }
        )

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        # Should still only have 2 comments (empty one skipped)
        assert len(document.raw_data["comments"]) == 2

    async def test_skips_checklists_with_no_items(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that checklists with no items are skipped."""
        private_board_artifact.content.checklists.append(
            {
                "id": "checklist-2",
                "name": "Empty Checklist",
                "checkItems": [],  # No items
            }
        )

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        # Should still only have 1 checklist (empty one skipped)
        assert len(document.raw_data["checklists"]) == 1

    async def test_skips_attachments_with_no_name(
        self, transformer: TrelloTransformer, private_board_artifact: TrelloCardArtifact
    ):
        """Test that attachments without names are skipped."""
        private_board_artifact.content.card_data["attachments"].append(
            {
                "id": "attachment-2",
                "name": "",  # Empty name
                "url": "https://trello.com/attachments/unnamed",
            }
        )

        document = await transformer._create_document(private_board_artifact)

        assert document is not None
        # Should still only have 1 attachment (unnamed one skipped)
        assert len(document.raw_data["attachments"]) == 1
