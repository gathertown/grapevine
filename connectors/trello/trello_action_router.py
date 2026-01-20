"""Trello webhook action router for classifying and routing webhook events.

This module categorizes Trello webhook actions by type and determines
the appropriate handler for each action.
"""

from enum import Enum


class TrelloActionHandler(str, Enum):
    """Handler types for different categories of Trello webhook actions."""

    CARD_CONTENT = "card_content"  # Full card re-index (content changes)
    CARD_METADATA = "card_metadata"  # Card metadata update (attachments, members, labels)
    CARD_MOVEMENT = "card_movement"  # Card moved between boards/lists
    BOARD_DISCOVERY = "board_discovery"  # New board created/discovered
    DELETION = "deletion"  # Card/board deleted (pruning)
    ADMIN_LIFECYCLE = "admin_lifecycle"  # Admin demoted/removed (CRITICAL)
    METADATA_ONLY = "metadata_only"  # Update artifacts (not indexed)
    IGNORE = "ignore"  # No action needed


class TrelloActionRouter:
    """Routes Trello webhook actions to appropriate handlers.

    Member-level webhook receives ALL actions from ALL boards across ALL organizations.
    This router categorizes actions to determine the appropriate processing strategy.
    """

    # Events that trigger full card re-indexing
    CARD_CONTENT_ACTIONS = {
        "createCard",  # New card created
        "updateCard",  # Card content/description updated
        "commentCard",  # Comment added to card
        "copyCard",  # Card copied
    }

    # Events that trigger card metadata updates (lighter re-index)
    CARD_METADATA_ACTIONS = {
        "addAttachmentToCard",  # Attachment added
        "deleteAttachmentFromCard",  # Attachment removed
        "addChecklistToCard",  # Checklist added
        "removeChecklistFromCard",  # Checklist removed
        "createCheckItem",  # Checklist item added
        "deleteCheckItem",  # Checklist item removed
        "updateCheckItemStateOnCard",  # Checklist item checked/unchecked
        "addMemberToCard",  # Member assigned
        "removeMemberFromCard",  # Member removed
        "addLabelToCard",  # Label added
        "removeLabelFromCard",  # Label removed
    }

    # Events that trigger card movement processing
    CARD_MOVEMENT_ACTIONS = {
        "moveCardToBoard",  # Card moved to this board
        "moveCardFromBoard",  # Card moved away from this board
        "updateList",  # List renamed (affects card metadata)
    }

    # Events that trigger board discovery and backfill
    BOARD_DISCOVERY_ACTIONS = {
        "createBoard",  # New board created
        "addToOrganizationBoard",  # Board added to organization
        "copyBoard",  # Board copied
    }

    # Events that trigger card/board deletion (pruning)
    DELETION_ACTIONS = {
        "deleteCard",  # Card deleted
        "closeBoard",  # Board closed
        "deleteBoard",  # Board deleted (rare, usually closed)
    }

    # CRITICAL: Admin privilege changes
    # These are the LAST admin-privileged actions we'll receive
    ADMIN_LIFECYCLE_ACTIONS = {
        "makeNormalMemberOfOrganization",  # Admin demoted to normal member
        "removeMemberFromOrganization",  # Admin removed from organization
    }

    # Events that update metadata artifacts (not indexed content)
    METADATA_ONLY_ACTIONS = {
        "updateBoard",  # Board name/description changed
        "updateOrganization",  # Organization metadata changed
    }

    IGNORED_ACTIONS = {
        # Member profile changes (GDPR compliance)
        # NOTE: updateMember is DEPRECATED by Trello and not reliably sent via webhooks.
        # We handle member profile updates via Trello's Compliance API polling instead.
        # See: TrelloCompliancePoller.handle_member_profile_update()
        "updateMember",  # Member profile changed (deprecated webhook event)
        "addMemberToBoard",  # Board membership (doesn't affect card content)
        "removeMemberFromBoard",  # Board membership
        "makeAdminOfBoard",  # Board admin status
        "makeNormalMemberOfBoard",  # Board member status
        "addMemberToOrganization",  # Org membership
        "makeAdminOfOrganization",  # Org admin status
        "acceptEnterpriseJoinRequest",  # Enterprise management
        "addOrganizationToEnterprise",  # Enterprise management
        "removeOrganizationFromEnterprise",  # Enterprise management
        "createBoardPreference",  # Board settings
    }

    @classmethod
    def get_handler(cls, action_type: str) -> TrelloActionHandler:
        """Determine the appropriate handler for a Trello action.

        Args:
            action_type: The Trello action type (e.g., "createCard", "updateBoard")

        Returns:
            TrelloActionHandler enum indicating which handler should process this action
        """
        if action_type in cls.ADMIN_LIFECYCLE_ACTIONS:
            return TrelloActionHandler.ADMIN_LIFECYCLE

        if action_type in cls.CARD_CONTENT_ACTIONS:
            return TrelloActionHandler.CARD_CONTENT

        if action_type in cls.CARD_METADATA_ACTIONS:
            return TrelloActionHandler.CARD_METADATA

        if action_type in cls.CARD_MOVEMENT_ACTIONS:
            return TrelloActionHandler.CARD_MOVEMENT

        if action_type in cls.BOARD_DISCOVERY_ACTIONS:
            return TrelloActionHandler.BOARD_DISCOVERY

        if action_type in cls.DELETION_ACTIONS:
            return TrelloActionHandler.DELETION

        if action_type in cls.METADATA_ONLY_ACTIONS:
            return TrelloActionHandler.METADATA_ONLY

        if action_type in cls.IGNORED_ACTIONS:
            return TrelloActionHandler.IGNORE

        return TrelloActionHandler.IGNORE

    @classmethod
    def should_process(cls, action_type: str) -> bool:
        """Check if an action should be processed (not ignored).

        Args:
            action_type: The Trello action type

        Returns:
            True if action should be processed, False if it should be ignored
        """
        handler = cls.get_handler(action_type)
        return handler != TrelloActionHandler.IGNORE
