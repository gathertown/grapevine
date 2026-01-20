"""Tests for Trello webhook action router.

This module tests the routing of Trello webhook actions to appropriate handlers.
"""

from connectors.trello.trello_action_router import TrelloActionHandler, TrelloActionRouter


class TestTrelloActionRouter:
    """Test suite for Trello action router."""

    def test_card_content_actions(self):
        """Test that card content actions are routed correctly."""
        actions = ["createCard", "updateCard", "commentCard", "copyCard"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.CARD_CONTENT

    def test_card_metadata_actions(self):
        """Test that card metadata actions are routed correctly."""
        actions = [
            "addAttachmentToCard",
            "deleteAttachmentFromCard",
            "addChecklistToCard",
            "removeChecklistFromCard",
            "updateCheckItemStateOnCard",
            "addMemberToCard",
            "removeMemberFromCard",
            "addLabelToCard",
            "removeLabelFromCard",
        ]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.CARD_METADATA

    def test_card_movement_actions(self):
        """Test that card movement actions are routed correctly."""
        actions = ["moveCardToBoard", "moveCardFromBoard", "updateList"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.CARD_MOVEMENT

    def test_board_discovery_actions(self):
        """Test that board discovery actions are routed correctly."""
        actions = ["createBoard", "addToOrganizationBoard", "copyBoard"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.BOARD_DISCOVERY

    def test_deletion_actions(self):
        """Test that deletion actions are routed correctly."""
        actions = ["deleteCard", "closeBoard", "deleteBoard"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.DELETION

    def test_admin_lifecycle_actions(self):
        """Test that admin lifecycle actions are routed correctly."""
        actions = ["makeNormalMemberOfOrganization", "removeMemberFromOrganization"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.ADMIN_LIFECYCLE

    def test_metadata_only_actions(self):
        """Test that metadata-only actions are routed correctly."""
        actions = ["updateBoard", "updateOrganization"]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.METADATA_ONLY

    def test_ignored_actions(self):
        """Test that ignored actions are routed correctly."""
        actions = [
            "addMemberToBoard",
            "removeMemberFromBoard",
            "makeAdminOfBoard",
            "makeNormalMemberOfBoard",
            "addMemberToOrganization",
            "makeAdminOfOrganization",
            "acceptEnterpriseJoinRequest",
            "addOrganizationToEnterprise",
            "removeOrganizationFromEnterprise",
            "createBoardPreference",
            "updateMember",
        ]

        for action in actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.IGNORE

    def test_unknown_action_type(self):
        """Test that unknown action types default to IGNORE."""
        unknown_actions = [
            "unknownAction",
            "someRandomEvent",
            "completelyMadeUp",
        ]

        for action in unknown_actions:
            handler = TrelloActionRouter.get_handler(action)
            assert handler == TrelloActionHandler.IGNORE

    def test_should_process_returns_true_for_actionable_events(self):
        """Test that should_process returns True for events that need processing."""
        actionable = [
            "createCard",
            "deleteCard",
            "createBoard",
            "makeNormalMemberOfOrganization",
        ]

        for action in actionable:
            assert TrelloActionRouter.should_process(action) is True

    def test_should_process_returns_false_for_ignored_events(self):
        """Test that should_process returns False for ignored events."""
        ignored = [
            "addMemberToBoard",
            "updateMember",
            "unknownAction",
        ]

        for action in ignored:
            assert TrelloActionRouter.should_process(action) is False

    def test_admin_lifecycle_has_highest_priority(self):
        """Test that admin lifecycle actions are checked first (highest priority)."""
        # This is important because these are critical events
        handler = TrelloActionRouter.get_handler("makeNormalMemberOfOrganization")
        assert handler == TrelloActionHandler.ADMIN_LIFECYCLE

        handler = TrelloActionRouter.get_handler("removeMemberFromOrganization")
        assert handler == TrelloActionHandler.ADMIN_LIFECYCLE
