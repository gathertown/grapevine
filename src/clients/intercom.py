import sys
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class IntercomConversation(BaseModel):
    """Intercom conversation model."""

    id: str
    type: str
    created_at: int
    updated_at: int
    state: str
    priority: str | None = None
    title: str | None = None


class IntercomClient:
    """A client for interacting with the Intercom REST API."""

    API_BASE_URL = "https://api.intercom.io"

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Intercom access token is required and cannot be empty")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Intercom-Version": "2.10",  # Use stable API version
            }
        )

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        """Make a request to the Intercom API.

        Args:
            endpoint: API endpoint path (e.g., "/conversations")
            method: HTTP method (GET, POST, PUT, DELETE)
            params: Optional query parameters
            json_body: Optional JSON body for POST/PUT requests
            api_version: Optional API version override (defaults to session default)

        Returns:
            API response as dict

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        url = f"{self.API_BASE_URL}{endpoint}"

        # Use custom API version if provided, otherwise use session default
        headers = {}
        if api_version:
            headers["Intercom-Version"] = api_version

        try:
            if method == "GET":
                response = self.session.get(url, params=params, headers=headers)
            elif method == "POST":
                response = self.session.post(url, params=params, json=json_body, headers=headers)
            elif method == "PUT":
                response = self.session.put(url, params=params, json=json_body, headers=headers)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Intercom API rate limit hit, retrying after {retry_after}s")
                raise RateLimitedError(retry_after=retry_after)

            response.raise_for_status()

            # Handle empty responses
            if not response.content:
                return {}

            return response.json()

        except RateLimitedError:
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Intercom API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Intercom API request error: {e}")
            raise

    @rate_limited(max_retries=5, base_delay=1)
    def get_conversations(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get conversations from Intercom.

        Args:
            per_page: Number of conversations per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing conversations and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 150),  # Intercom max is 150
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/conversations", params=params)

        logger.debug(f"Retrieved {len(response.get('conversations', []))} conversations")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def search_conversations(
        self,
        updated_at_after: int | None = None,
        per_page: int = 50,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """Search conversations using the Intercom search API.

        Args:
            updated_at_after: Unix timestamp - only return conversations updated after this time
            per_page: Number of conversations per page (max 150 for search)
            starting_after: Cursor for pagination

        Returns:
            API response containing conversations and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        # Build query with updated_at filter
        query_value = []
        if updated_at_after is not None:
            query_value.append(
                {
                    "field": "updated_at",
                    "operator": ">",
                    "value": str(updated_at_after),
                }
            )

        # If no filters, return empty result
        # Note: Callers should use get_conversations() for full backfills without filters
        if not query_value:
            return {"conversations": [], "pages": {}}

        request_body: dict[str, Any] = {
            "query": {
                "operator": "AND",
                "value": query_value,
            },
            "pagination": {
                "per_page": min(per_page, 150),  # Search API max is 150
            },
        }

        if starting_after:
            request_body["pagination"]["starting_after"] = starting_after

        response = self._make_request(
            "/conversations/search",
            method="POST",
            json_body=request_body,
            api_version="2.14",  # Search API requires version 2.14+
        )

        logger.debug(
            f"Retrieved {len(response.get('conversations', []))} conversations from search"
        )

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        """Get a specific conversation by ID.

        Args:
            conversation_id: The conversation ID

        Returns:
            Conversation data

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        response = self._make_request(f"/conversations/{conversation_id}")

        logger.debug(f"Retrieved conversation {conversation_id}")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_me(self) -> dict[str, Any]:
        """Get information about the current app/admin.

        Returns:
            App and admin information

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        response = self._make_request("/me")

        logger.debug("Retrieved app/admin information")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_articles(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get articles from Intercom Help Center.

        Args:
            per_page: Number of articles per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing articles and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 150),  # Intercom max is 150
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/articles", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} articles")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def search_articles(
        self,
        updated_at_after: int | None = None,
        per_page: int = 50,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """Search articles using the Intercom search API.

        Args:
            updated_at_after: Unix timestamp - only return articles updated after this time
            per_page: Number of articles per page (max 150 for search)
            starting_after: Cursor for pagination

        Returns:
            API response containing articles and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        # Build query with updated_at filter
        query_value = []
        if updated_at_after is not None:
            query_value.append(
                {
                    "field": "updated_at",
                    "operator": ">",
                    "value": str(updated_at_after),
                }
            )

        # If no filters, return empty result
        # Note: Callers should use get_articles() for full backfills without filters
        if not query_value:
            return {"data": [], "pages": {}}

        request_body: dict[str, Any] = {
            "query": {
                "operator": "AND",
                "value": query_value,
            },
            "pagination": {
                "per_page": min(per_page, 150),  # Search API max is 150
            },
        }

        if starting_after:
            request_body["pagination"]["starting_after"] = starting_after

        response = self._make_request(
            "/articles/search",
            method="POST",
            json_body=request_body,
            api_version="2.14",  # Search API requires version 2.14+
        )

        logger.debug(f"Retrieved {len(response.get('data', []))} articles from search")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_article(self, article_id: str) -> dict[str, Any]:
        """Get a specific article by ID.

        Args:
            article_id: The article ID

        Returns:
            Article data

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        response = self._make_request(f"/articles/{article_id}")

        logger.debug(f"Retrieved article {article_id}")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_collections(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get collections from Intercom Help Center.

        Args:
            per_page: Number of collections per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing collections and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 150),
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/help_center/collections", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} collections")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_sections(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get sections from Intercom Help Center.

        Args:
            per_page: Number of sections per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing sections and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 150),
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/help_center/sections", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} sections")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def search_contacts(
        self,
        updated_at_after: int | None = None,
        per_page: int = 50,
        starting_after: str | None = None,
    ) -> dict[str, Any]:
        """Search contacts using the Intercom search API.

        Args:
            updated_at_after: Unix timestamp - only return contacts updated after this time
            per_page: Number of contacts per page (max 150 for search)
            starting_after: Cursor for pagination

        Returns:
            API response containing contacts and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        # Build query with updated_at filter
        query_value = []
        if updated_at_after is not None:
            query_value.append(
                {
                    "field": "updated_at",
                    "operator": ">",
                    "value": str(updated_at_after),
                }
            )

        # If no filters, return empty result
        # Note: Callers should use get_contacts() for full backfills without filters
        if not query_value:
            return {"data": [], "pages": {}}

        request_body: dict[str, Any] = {
            "query": {
                "operator": "AND",
                "value": query_value,
            },
            "pagination": {
                "per_page": min(per_page, 150),  # Search API max is 150
            },
        }

        if starting_after:
            request_body["pagination"]["starting_after"] = starting_after

        response = self._make_request(
            "/contacts/search",
            method="POST",
            json_body=request_body,
            api_version="2.14",  # Search API requires version 2.14+
        )

        logger.debug(f"Retrieved {len(response.get('data', []))} contacts from search")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_contacts(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get contacts from Intercom.

        Args:
            per_page: Number of contacts per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing contacts and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 150),  # Intercom max is 150
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/contacts", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} contacts")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Get a specific contact by ID.

        Args:
            contact_id: The contact ID

        Returns:
            Contact data

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        response = self._make_request(f"/contacts/{contact_id}")

        logger.debug(f"Retrieved contact {contact_id}")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_companies(
        self,
        per_page: int = 50,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        """Get companies from Intercom.

        Args:
            per_page: Number of companies per page (max 150)
            starting_after: Cursor for pagination
            order: Sort order ("asc" or "desc")

        Returns:
            API response containing companies and pagination info

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        params: dict[str, Any] = {
            "per_page": min(per_page, 50),  # Intercom Companies API max is 50
            "order": order,
        }

        if starting_after:
            params["starting_after"] = starting_after

        response = self._make_request("/companies", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} companies")

        return response

    @rate_limited(max_retries=5, base_delay=1)
    def get_company(self, company_id: str) -> dict[str, Any]:
        """Get a specific company by ID.

        Args:
            company_id: The company ID

        Returns:
            Company data

        Raises:
            RateLimitedError: When rate limited by Intercom
            requests.exceptions.HTTPError: For other HTTP errors
        """
        response = self._make_request(f"/companies/{company_id}")

        logger.debug(f"Retrieved company {company_id}")

        return response


async def get_intercom_client_for_tenant(tenant_id: str, ssm_client: SSMClient) -> IntercomClient:
    """Factory method to get Intercom client with proper OAuth authentication.

    Args:
        tenant_id: Tenant ID
        ssm_client: SSM client for retrieving secrets

    Returns:
        IntercomClient configured with valid access token

    Raises:
        ValueError: If no access token is found for the tenant
    """
    # Get access token from SSM Parameter Store
    access_token = await ssm_client.get_api_key(tenant_id, "INTERCOM_ACCESS_TOKEN")

    if not access_token:
        raise ValueError(f"No Intercom access token configured for tenant {tenant_id}")

    # Log credential source with token redaction
    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Intercom client credentials loaded",
        tenant_id=tenant_id,
        token_source="SSM Parameter Store",
        token_preview=redacted_token,
    )

    return IntercomClient(access_token=access_token)
