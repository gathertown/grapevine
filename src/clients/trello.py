"""Trello API client for interacting with the Trello REST API."""

import sys
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from src.utils.logging import get_logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class TrelloBoard(BaseModel):
    """Represents a Trello board with basic metadata."""

    id: str
    name: str
    closed: bool = False
    desc: str | None = None


class TrelloClient:
    """A client for interacting with the Trello REST API.

    Uses Power-Up API key (shared across all tenants) and per-tenant OAuth tokens.
    API documentation: https://developer.atlassian.com/cloud/trello/rest/
    """

    API_BASE_URL = "https://api.trello.com/1"

    # Trello API limits
    MAX_ACTIONS_PER_REQUEST = 1000  # Trello's maximum limit per API call
    DEFAULT_MAX_ACTIONS_PAGINATED = 5000  # Default max for paginated fetches

    def __init__(self, api_key: str, api_token: str | None = None):
        if not api_key:
            raise ValueError("Trello API key is required and cannot be empty")

        self.api_key = api_key
        self.api_token = api_token
        self.session = requests.Session()

    @rate_limited(max_retries=5, base_delay=1)
    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make a request to the Trello API.

        Args:
            endpoint: API endpoint path (e.g., "/members/me/boards")
            method: HTTP method (GET, POST, PUT, DELETE)
            params: Optional query parameters
            json_body: Optional JSON body for POST/PUT requests

        Returns:
            API response as dict or list

        Raises:
            RateLimitedError: When rate limited by Trello
            requests.exceptions.HTTPError: For other HTTP errors
        """
        url = f"{self.API_BASE_URL}{endpoint}"

        # Add authentication to params
        request_params = params.copy() if params else {}
        request_params["key"] = self.api_key
        if self.api_token:
            request_params["token"] = self.api_token
        else:
            raise ValueError(
                "API token is required for this endpoint. "
                "Initialize TrelloClient with an api_token for standard API calls."
            )

        try:
            if method == "GET":
                response = self.session.get(url, params=request_params)
            elif method == "POST":
                response = self.session.post(url, params=request_params, json=json_body)
            elif method == "PUT":
                response = self.session.put(url, params=request_params, json=json_body)
            elif method == "DELETE":
                response = self.session.delete(url, params=request_params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Some DELETE requests may not return JSON
            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

        except requests.exceptions.HTTPError as e:
            # Trello returns 429 for rate limiting
            if e.response.status_code == 429:
                # Trello may provide Retry-After header
                retry_after = int(e.response.headers.get("Retry-After", 10))
                logger.warning(f"Trello API rate limited, retry after {retry_after}s")
                raise RateLimitedError(retry_after=retry_after)
            else:
                logger.error(
                    f"Trello API request failed - Method: {method}, Status: {e.response.status_code}, "
                    f"Error: {e.response.text}"
                )
                raise

        except requests.exceptions.RequestException as e:
            logger.error(f"Trello API request error: {e}")
            raise

    def get_boards(self, member: str = "me", filter_type: str = "open") -> list[TrelloBoard]:
        """Get all boards for a member.

        Args:
            member: Member ID or "me" for authenticated user (default: "me")
            filter_type: Filter for boards - "open", "closed", "all" (default: "open")

        Returns:
            List of TrelloBoard objects

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-members/#api-members-id-boards-get
        """
        endpoint = f"/members/{member}/boards"
        params = {
            "fields": "id,name,closed,desc,shortUrl,url,dateLastActivity,idOrganization",
            "filter": filter_type,
        }

        try:
            boards_data = self._make_request(endpoint, params=params)
            if not isinstance(boards_data, list):
                logger.error(f"Expected list from boards endpoint, got {type(boards_data)}")
                return []

            boards = [
                TrelloBoard(
                    id=board["id"],
                    name=board["name"],
                    closed=board.get("closed", False),
                    desc=board.get("desc"),
                )
                for board in boards_data
            ]

            logger.info(f"Retrieved {len(boards)} boards for member {member}")
            return boards

        except Exception as e:
            logger.error(f"Failed to fetch boards for member {member}: {e}")
            raise

    def get_board(self, board_id: str) -> dict[str, Any]:
        """Get a single board by ID with full details.

        Args:
            board_id: Board ID

        Returns:
            Board data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-get
        """
        endpoint = f"/boards/{board_id}"
        params = {
            "fields": "all",
        }

        try:
            board_data = self._make_request(endpoint, params=params)
            logger.debug(f"Retrieved board {board_id}")
            return board_data

        except Exception as e:
            logger.error(f"Failed to fetch board {board_id}: {e}")
            raise

    def get_cards_on_board(self, board_id: str) -> list[dict[str, Any]]:
        """Get all cards on a board.

        Args:
            board_id: Board ID

        Returns:
            List of card data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-cards-get
        """
        endpoint = f"/boards/{board_id}/cards"
        params = {
            "fields": "all",
            "members": "true",  # Include member info
            "member_fields": "all",
            "checklists": "all",  # Include all checklists
            "attachments": "true",  # Include attachments
        }

        try:
            cards_data = self._make_request(endpoint, params=params)
            if not isinstance(cards_data, list):
                logger.error(f"Expected list from cards endpoint, got {type(cards_data)}")
                return []

            logger.info(f"Retrieved {len(cards_data)} cards from board {board_id}")
            return cards_data

        except Exception as e:
            logger.error(f"Failed to fetch cards for board {board_id}: {e}")
            raise

    def get_card(self, card_id: str) -> dict[str, Any]:
        """Get a single card by ID with full details.

        Args:
            card_id: Card ID

        Returns:
            Card data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-cards/#api-cards-id-get
        """
        endpoint = f"/cards/{card_id}"
        params = {
            "fields": "all",
            "members": "true",
            "member_fields": "all",
            "checklists": "all",
            "attachments": "true",
            "board": "true",  # Include board info
            "board_fields": "name",
            "list": "true",  # Include list info
            "list_fields": "name",
        }

        try:
            card_data = self._make_request(endpoint, params=params)
            logger.debug(f"Retrieved card {card_id}")
            return card_data

        except Exception as e:
            logger.error(f"Failed to fetch card {card_id}: {e}")
            raise

    def get_card_actions(
        self, card_id: str, filter_types: str = "commentCard"
    ) -> list[dict[str, Any]]:
        """Get actions (comments, moves, etc.) for a card.

        Args:
            card_id: Card ID
            filter_types: Comma-separated action types to include (default: "commentCard")
                         Examples: "commentCard", "updateCard", "addMemberToCard"

        Returns:
            List of action data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-cards/#api-cards-id-actions-get
        """
        endpoint = f"/cards/{card_id}/actions"
        params = {
            "filter": filter_types,
            "fields": "all",
            "memberCreator": "true",
            "memberCreator_fields": "all",
        }

        try:
            actions_data = self._make_request(endpoint, params=params)
            if not isinstance(actions_data, list):
                logger.error(f"Expected list from actions endpoint, got {type(actions_data)}")
                return []

            logger.debug(f"Retrieved {len(actions_data)} actions for card {card_id}")
            return actions_data

        except Exception as e:
            logger.error(f"Failed to fetch actions for card {card_id}: {e}")
            raise

    def get_lists_on_board(self, board_id: str) -> list[dict[str, Any]]:
        """Get all lists on a board.

        Args:
            board_id: Board ID

        Returns:
            List of list data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-lists-get
        """
        endpoint = f"/boards/{board_id}/lists"
        params = {
            "fields": "all",
        }

        try:
            lists_data = self._make_request(endpoint, params=params)
            if not isinstance(lists_data, list):
                logger.error(f"Expected list from lists endpoint, got {type(lists_data)}")
                return []

            logger.debug(f"Retrieved {len(lists_data)} lists from board {board_id}")
            return lists_data

        except Exception as e:
            logger.error(f"Failed to fetch lists for board {board_id}: {e}")
            raise

    def get_members_on_board(self, board_id: str) -> list[dict[str, Any]]:
        """Get all members on a board.

        Args:
            board_id: Board ID

        Returns:
            List of member data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-members-get
        """
        endpoint = f"/boards/{board_id}/members"
        params = {
            "fields": "all",
        }

        try:
            members_data = self._make_request(endpoint, params=params)
            if not isinstance(members_data, list):
                logger.error(f"Expected list from members endpoint, got {type(members_data)}")
                return []

            logger.debug(f"Retrieved {len(members_data)} members from board {board_id}")
            return members_data

        except Exception as e:
            logger.error(f"Failed to fetch members for board {board_id}: {e}")
            raise

    def get_member(self, member: str = "me") -> dict[str, Any]:
        """Get member information.

        Args:
            member: Member ID or "me" for authenticated user (default: "me")

        Returns:
            Member data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-members/#api-members-id-get
        """
        endpoint = f"/members/{member}"
        params = {
            "fields": "all",
        }

        try:
            member_data = self._make_request(endpoint, params=params)
            logger.debug(f"Retrieved member info for {member}")
            return member_data

        except Exception as e:
            logger.error(f"Failed to fetch member {member}: {e}")
            raise

    def get_organizations(self, member: str = "me") -> list[dict[str, Any]]:
        """Get all organizations/workspaces for a member.

        Args:
            member: Member ID or "me" for authenticated user (default: "me")

        Returns:
            List of organization/workspace data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-members/#api-members-id-organizations-get
        """
        endpoint = f"/members/{member}/organizations"
        params = {
            "fields": "all",
        }

        try:
            orgs_data = self._make_request(endpoint, params=params)
            if not isinstance(orgs_data, list):
                logger.error(f"Expected list from organizations endpoint, got {type(orgs_data)}")
                return []

            logger.info(f"Retrieved {len(orgs_data)} organizations for member {member}")
            return orgs_data

        except Exception as e:
            logger.error(f"Failed to fetch organizations for member {member}: {e}")
            raise

    def get_organization_member(self, org_id: str, member_id: str) -> dict[str, Any]:
        """Get a specific member's details in an organization.

        This is useful for checking if a member is an admin of the organization.

        Args:
            org_id: Organization ID
            member_id: Member ID

        Returns:
            Organization membership data as dict containing 'memberType' field
            ('admin' or 'normal')

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-organizations/#api-organizations-id-members-idmember-get
        """
        endpoint = f"/organizations/{org_id}/members/{member_id}"
        params = {
            "fields": "all",
        }

        try:
            member_data = self._make_request(endpoint, params=params)
            logger.debug(
                f"Retrieved organization membership for member {member_id} in org {org_id}"
            )
            return member_data

        except Exception as e:
            logger.error(f"Failed to fetch org member {member_id} in org {org_id}: {e}")
            raise

    def get_organization(self, org_id: str) -> dict[str, Any]:
        """Get a single organization/workspace by ID with full details.

        Args:
            org_id: Organization ID

        Returns:
            Organization data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-organizations/#api-organizations-id-get
        """
        endpoint = f"/organizations/{org_id}"
        params = {
            "fields": "all",
        }

        try:
            org_data = self._make_request(endpoint, params=params)
            logger.debug(f"Retrieved organization {org_id}")
            return org_data

        except Exception as e:
            logger.error(f"Failed to fetch organization {org_id}: {e}")
            raise

    def get_organization_boards(
        self, org_id: str, filter_type: str = "open"
    ) -> list[dict[str, Any]]:
        """Get all boards belonging to an organization.

        Args:
            org_id: Organization ID
            filter_type: Filter for boards - "open", "closed", "all" (default: "open")

        Returns:
            List of board data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-organizations/#api-organizations-id-boards-get
        """
        endpoint = f"/organizations/{org_id}/boards"
        params = {
            "fields": "id,name,closed,desc,shortUrl,url,dateLastActivity,idOrganization",
            "filter": filter_type,
        }

        try:
            boards_data = self._make_request(endpoint, params=params)
            if not isinstance(boards_data, list):
                logger.error(
                    f"Expected list from organization boards endpoint, got {type(boards_data)}"
                )
                return []

            logger.info(f"Retrieved {len(boards_data)} boards for organization {org_id}")
            return boards_data

        except Exception as e:
            logger.error(f"Failed to fetch boards for organization {org_id}: {e}")
            raise

    def create_webhook(
        self, callback_url: str, id_model: str, description: str | None = None
    ) -> dict[str, Any]:
        """Create a webhook for a Trello model (board, card, etc.).

        Args:
            callback_url: The URL to receive webhook POST requests
            id_model: The ID of the model to watch (board ID, card ID, etc.)
            description: Optional description for the webhook

        Returns:
            Webhook data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-webhooks/#api-webhooks-post
        """
        endpoint = "/webhooks"
        params = {
            "callbackURL": callback_url,
            "idModel": id_model,
        }

        if description:
            params["description"] = description

        try:
            webhook_data = self._make_request(endpoint, method="POST", params=params)
            logger.info(f"Created webhook {webhook_data.get('id')} for model {id_model}")
            return webhook_data

        except Exception as e:
            logger.error(f"Failed to create webhook for model {id_model}: {e}")
            raise

    def get_webhooks(self) -> list[dict[str, Any]]:
        """Get all webhooks for the authenticated token.

        Returns:
            List of webhook data dicts

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-tokens/#api-tokens-token-webhooks-get
        """
        endpoint = f"/tokens/{self.api_token}/webhooks"

        try:
            webhooks_data = self._make_request(endpoint)
            if not isinstance(webhooks_data, list):
                logger.error(f"Expected list from webhooks endpoint, got {type(webhooks_data)}")
                return []

            logger.info(f"Retrieved {len(webhooks_data)} webhooks")
            return webhooks_data

        except Exception as e:
            logger.error(f"Failed to fetch webhooks: {e}")
            raise

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Get a single webhook by ID.

        Args:
            webhook_id: Webhook ID

        Returns:
            Webhook data as dict

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-webhooks/#api-webhooks-id-get
        """
        endpoint = f"/webhooks/{webhook_id}"

        try:
            webhook_data = self._make_request(endpoint)
            logger.debug(f"Retrieved webhook {webhook_id}")
            return webhook_data

        except Exception as e:
            logger.error(f"Failed to fetch webhook {webhook_id}: {e}")
            raise

    def delete_webhook(self, webhook_id: str) -> None:
        """Delete a webhook by ID.

        Args:
            webhook_id: Webhook ID

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-webhooks/#api-webhooks-id-delete
        """
        endpoint = f"/webhooks/{webhook_id}"

        try:
            self._make_request(endpoint, method="DELETE")
            logger.info(f"Deleted webhook {webhook_id}")

        except Exception as e:
            logger.error(f"Failed to delete webhook {webhook_id}: {e}")
            raise

    def get_board_actions(
        self,
        board_id: str,
        since: str | None = None,
        before: str | None = None,
        filter_types: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get actions on a board, optionally filtered by date.

        This is the key method for incremental sync - it returns all actions
        (card creates, updates, comments, moves, deletions, etc.) on a board
        since a given date. From these actions, we can identify which cards
        were modified and need to be re-indexed.

        Args:
            board_id: Board ID
            since: ISO 8601 timestamp or action ID to get actions after
            before: ISO 8601 timestamp or action ID to get actions before
            filter_types: Comma-separated action types to include. If None, returns all.
                         Card-related types: createCard, updateCard, deleteCard,
                         commentCard, copyCard, moveCardToBoard, moveCardFromBoard,
                         addAttachmentToCard, addChecklistToCard, addMemberToCard,
                         addLabelToCard, removeChecklistFromCard, removeMemberFromCard,
                         removeLabelFromCard, updateCheckItemStateOnCard
            limit: Maximum number of actions to return (default/max: MAX_ACTIONS_PER_REQUEST)

        Returns:
            List of action data dicts, each containing:
            - id: Action ID
            - type: Action type (e.g., "updateCard", "commentCard")
            - date: ISO 8601 timestamp
            - data: Action-specific data including card info
            - memberCreator: Member who performed the action

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-actions-get
        """
        endpoint = f"/boards/{board_id}/actions"
        effective_limit = min(limit or self.MAX_ACTIONS_PER_REQUEST, self.MAX_ACTIONS_PER_REQUEST)
        params: dict[str, str | int] = {
            "limit": effective_limit,
        }

        if since:
            params["since"] = since
        if before:
            params["before"] = before
        if filter_types:
            params["filter"] = filter_types

        try:
            actions_data = self._make_request(endpoint, params=params)
            if not isinstance(actions_data, list):
                logger.error(f"Expected list from board actions endpoint, got {type(actions_data)}")
                return []

            logger.info(
                f"Retrieved {len(actions_data)} actions from board {board_id}"
                + (f" since {since}" if since else "")
            )
            return actions_data

        except Exception as e:
            logger.error(f"Failed to fetch actions for board {board_id}: {e}")
            raise

    def get_board_actions_paginated(
        self,
        board_id: str,
        since: str | None = None,
        filter_types: str | None = None,
        max_actions: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for a board with pagination support.

        Trello limits action queries to MAX_ACTIONS_PER_REQUEST at a time.
        This method handles pagination automatically using the 'before' parameter
        to fetch older actions until we reach the 'since' date or max_actions limit.

        Args:
            board_id: Board ID
            since: ISO 8601 timestamp or action ID to get actions after
            filter_types: Comma-separated action types to include. If None, returns all.
            max_actions: Maximum total actions to retrieve (default: DEFAULT_MAX_ACTIONS_PAGINATED)

        Returns:
            List of all action data dicts within the time range, newest first

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-boards/#api-boards-id-actions-get
        """
        effective_max = max_actions or self.DEFAULT_MAX_ACTIONS_PAGINATED
        all_actions: list[dict[str, Any]] = []
        before: str | None = None

        while len(all_actions) < effective_max:
            actions = self.get_board_actions(
                board_id=board_id,
                since=since,
                before=before,
                filter_types=filter_types,
            )

            if not actions:
                break

            all_actions.extend(actions)

            # If we got less than max per request, we've reached the end
            if len(actions) < self.MAX_ACTIONS_PER_REQUEST:
                break

            # Use the oldest action's ID as the 'before' cursor for next page
            # Actions are returned newest-first, so last item is oldest
            oldest_action = actions[-1]
            before = oldest_action.get("id")

            if not before:
                break

        logger.info(
            f"Retrieved {len(all_actions)} total actions for board {board_id}"
            + (f" since {since}" if since else "")
        )
        return all_actions

    def get_member_actions(
        self,
        member: str = "me",
        since: str | None = None,
        before: str | None = None,
        filter_types: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for a member across all boards, optionally filtered by date.

        This endpoint captures ALL actions taken by or affecting the member,
        including actions on boards that have since been deleted or closed.
        This is critical for incremental sync to properly handle deletions.

        Args:
            member: Member ID or "me" for authenticated user (default: "me")
            since: ISO 8601 timestamp or action ID to get actions after
            before: ISO 8601 timestamp or action ID to get actions before
            filter_types: Comma-separated action types to include. If None, returns all.
            limit: Maximum number of actions to return (default/max: MAX_ACTIONS_PER_REQUEST)

        Returns:
            List of action data dicts, each containing:
            - id: Action ID
            - type: Action type (e.g., "updateCard", "deleteCard", "deleteBoard")
            - date: ISO 8601 timestamp
            - data: Action-specific data including card/board info
            - memberCreator: Member who performed the action

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-members/#api-members-id-actions-get
        """
        endpoint = f"/members/{member}/actions"
        effective_limit = min(limit or self.MAX_ACTIONS_PER_REQUEST, self.MAX_ACTIONS_PER_REQUEST)
        params: dict[str, str | int] = {
            "limit": effective_limit,
        }

        if since:
            params["since"] = since
        if before:
            params["before"] = before
        if filter_types:
            params["filter"] = filter_types

        try:
            actions_data = self._make_request(endpoint, params=params)
            if not isinstance(actions_data, list):
                logger.error(
                    f"Expected list from member actions endpoint, got {type(actions_data)}"
                )
                return []

            logger.info(
                f"Retrieved {len(actions_data)} actions for member {member}"
                + (f" since {since}" if since else "")
            )
            return actions_data

        except Exception as e:
            logger.error(f"Failed to fetch actions for member {member}: {e}")
            raise

    def get_member_actions_paginated(
        self,
        member: str = "me",
        since: str | None = None,
        filter_types: str | None = None,
        max_actions: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for a member with pagination support.

        Trello limits action queries to MAX_ACTIONS_PER_REQUEST at a time.
        This method handles pagination automatically using the 'before' parameter
        to fetch older actions until we reach the 'since' date or max_actions limit.

        Args:
            member: Member ID or "me" for authenticated user (default: "me")
            since: ISO 8601 timestamp to get actions after (required for bounded queries)
            filter_types: Comma-separated action types to include. If None, returns all.
            max_actions: Maximum total actions to retrieve (default: DEFAULT_MAX_ACTIONS_PAGINATED)

        Returns:
            List of all action data dicts within the time range, newest first

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-members/#api-members-id-actions-get
        """
        effective_max = max_actions or self.DEFAULT_MAX_ACTIONS_PAGINATED
        all_actions: list[dict[str, Any]] = []
        before: str | None = None

        while len(all_actions) < effective_max:
            actions = self.get_member_actions(
                member=member,
                since=since,
                before=before,
                filter_types=filter_types,
            )

            if not actions:
                break

            all_actions.extend(actions)

            # If we got less than max per request, we've reached the end
            if len(actions) < self.MAX_ACTIONS_PER_REQUEST:
                break

            # Use the oldest action's ID as the 'before' cursor for next page
            # Actions are returned newest-first, so last item is oldest
            oldest_action = actions[-1]
            before = oldest_action.get("id")

            if not before:
                break

        logger.info(
            f"Retrieved {len(all_actions)} total actions for member {member}"
            + (f" since {since}" if since else "")
        )
        return all_actions

    def get_organization_actions(
        self,
        org_id: str,
        since: str | None = None,
        before: str | None = None,
        filter_types: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for an organization across ALL boards and ALL members.

        This endpoint captures ALL actions in the organization, regardless of
        which member performed them. This is the key endpoint for org-wide
        incremental sync.

        Args:
            org_id: Organization/Workspace ID
            since: ISO 8601 timestamp or action ID to get actions after
            before: ISO 8601 timestamp or action ID to get actions before
            filter_types: Comma-separated action types to include. If None, returns all.
            limit: Maximum number of actions to return (default/max: MAX_ACTIONS_PER_REQUEST)

        Returns:
            List of action data dicts, each containing:
            - id: Action ID
            - type: Action type (e.g., "updateCard", "deleteCard", "deleteBoard")
            - date: ISO 8601 timestamp
            - data: Action-specific data including card/board info
            - idMemberCreator: Member who performed the action

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-organizations/#api-organizations-id-actions-get
        """
        endpoint = f"/organizations/{org_id}/actions"
        effective_limit = min(limit or self.MAX_ACTIONS_PER_REQUEST, self.MAX_ACTIONS_PER_REQUEST)
        params: dict[str, str | int] = {
            "limit": effective_limit,
        }

        if since:
            params["since"] = since
        if before:
            params["before"] = before
        if filter_types:
            params["filter"] = filter_types

        try:
            actions_data = self._make_request(endpoint, params=params)
            if not isinstance(actions_data, list):
                logger.error(
                    f"Expected list from organization actions endpoint, got {type(actions_data)}"
                )
                return []

            logger.info(
                f"Retrieved {len(actions_data)} actions for organization {org_id}"
                + (f" since {since}" if since else "")
            )
            return actions_data

        except Exception as e:
            logger.error(f"Failed to fetch actions for organization {org_id}: {e}")
            raise

    def get_organization_actions_paginated(
        self,
        org_id: str,
        since: str | None = None,
        filter_types: str | None = None,
        max_actions: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all actions for an organization with pagination support.

        This fetches ALL actions across ALL boards and ALL members in the
        organization. Trello limits action queries to MAX_ACTIONS_PER_REQUEST
        at a time, so this method handles pagination automatically.

        Args:
            org_id: Organization/Workspace ID
            since: ISO 8601 timestamp or action ID to get actions after
            filter_types: Comma-separated action types to include. If None, returns all.
            max_actions: Maximum total actions to retrieve (default: DEFAULT_MAX_ACTIONS_PAGINATED)

        Returns:
            List of all action data dicts within the time range, newest first

        API Doc: https://developer.atlassian.com/cloud/trello/rest/api-group-organizations/#api-organizations-id-actions-get
        """
        effective_max = max_actions or self.DEFAULT_MAX_ACTIONS_PAGINATED
        all_actions: list[dict[str, Any]] = []
        before: str | None = None

        while len(all_actions) < effective_max:
            actions = self.get_organization_actions(
                org_id=org_id,
                since=since,
                before=before,
                filter_types=filter_types,
            )

            if not actions:
                break

            all_actions.extend(actions)

            # If we got less than max per request, we've reached the end
            if len(actions) < self.MAX_ACTIONS_PER_REQUEST:
                break

            # Use the oldest action's ID as the 'before' cursor for next page
            # Actions are returned newest-first, so last item is oldest
            oldest_action = actions[-1]
            before = oldest_action.get("id")

            if not before:
                break

        logger.info(
            f"Retrieved {len(all_actions)} total actions for organization {org_id}"
            + (f" since {since}" if since else "")
        )
        return all_actions

    def get_compliance_member_privacy(
        self, plugin_id: str, api_secret: str, since: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get GDPR compliance records for user deletions and profile updates.

        This endpoint must be polled at least once every 14 days to maintain GDPR compliance.

        NOTE: This endpoint uses different auth than standard Trello API endpoints.
        It requires 'key' + 'secret' parameters, NOT 'key' + 'token'.

        Args:
            plugin_id: Trello Power-Up plugin ID
            api_secret: Power-Up API secret (not OAuth secret)
            since: ISO 8601 timestamp to get records after (e.g., "2018-10-22 00:59:01Z")
            limit: Maximum number of records to return (default: 100)

        Returns:
            List of compliance records with the following structure:
            {
                "id": "string",  # Trello member ID
                "event": "accountUpdated" | "accountDeleted" | "tokenRevoked" | "tokenExpired",
                "date": "ISO 8601 timestamp",
                "alteredFields": ["bio", "username", ...] (for accountUpdated)
            }

        API Doc: https://developer.atlassian.com/cloud/trello/guides/compliance/personal-data-storage-gdpr/
        """
        url = f"{self.API_BASE_URL}/plugins/{plugin_id}/compliance/memberPrivacy"

        # Compliance API uses key + secret authentication, NOT key + token
        params: dict[str, str | int] = {
            "key": self.api_key,
            "secret": api_secret,
            "limit": limit,
        }

        if since:
            params["since"] = since

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()

            records = response.json()
            if not isinstance(records, list):
                logger.error(f"Expected list from compliance endpoint, got {type(records)}")
                return []

            logger.info(
                f"Retrieved {len(records)} compliance records"
                + (f" since {since}" if since else "")
            )
            return records

        except Exception as e:
            logger.error(f"Failed to fetch compliance records: {e}")
            raise
