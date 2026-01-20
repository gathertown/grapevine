"""
HubSpot API client for company data operations.
"""

import asyncio
import json
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from hubspot import HubSpot
from hubspot.crm.associations import ApiException as AssociationsApiException
from hubspot.crm.associations.v4 import ApiException as AssociationsV4ApiException
from hubspot.crm.companies import ApiException as CompaniesApiException
from hubspot.crm.contacts import ApiException as ContactsApiException
from hubspot.crm.deals import ApiException as DealsApiException
from hubspot.crm.objects import ApiException as ObjectsApiException
from hubspot.crm.objects.calls import ApiException as CallsApiException
from hubspot.crm.objects.communications import ApiException as CommunicationsApiException
from hubspot.crm.objects.emails import ApiException as EmailsApiException
from hubspot.crm.objects.meetings import ApiException as MeetingsApiException
from hubspot.crm.objects.notes import ApiException as NotesApiException
from hubspot.crm.objects.tasks import ApiException as TasksApiException
from hubspot.crm.pipelines import ApiException as PipelinesApiException
from hubspot.crm.properties import ApiException as PropertiesApiException
from hubspot.crm.tickets import ApiException as TicketsApiException

from src.clients.hubspot.hubspot_models import (
    HubSpotSearchDateFilter,
    HubSpotSearchOptions,
    HubSpotSearchReq,
    HubSpotSearchRes,
    build_search_request,
)
from src.utils.html_to_text import html_to_text_bs4
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

if TYPE_CHECKING:
    from src.ingest.services.hubspot_auth import HubspotAuthService

logger = get_logger(__name__)

# HubSpot API limit for companies per page
MAX_COMPANIES_PER_PAGE = 200
# Maximum retries for authentication errors
MAX_AUTH_RETRIES = 1

# 10_000 is HubSpot's maximum offset for search pagination
MAX_SEARCH_OFFSET = 10_000

type HubspotApiException = (
    AssociationsApiException
    | AssociationsV4ApiException
    | CompaniesApiException
    | ContactsApiException
    | DealsApiException
    | ObjectsApiException
    | PropertiesApiException
    | TicketsApiException
    | EmailsApiException
    | MeetingsApiException
    | NotesApiException
    | TasksApiException
    | CommunicationsApiException
    | CallsApiException
    | PipelinesApiException
)

HUBSPOT_API_EXCEPTIONS = (
    AssociationsApiException,
    AssociationsV4ApiException,
    CompaniesApiException,
    ContactsApiException,
    DealsApiException,
    ObjectsApiException,
    PropertiesApiException,
    TicketsApiException,
    EmailsApiException,
    MeetingsApiException,
    NotesApiException,
    TasksApiException,
    CommunicationsApiException,
    CallsApiException,
    PipelinesApiException,
)


@dataclass
class HubSpotProperty:
    name: str
    label: str
    type: str
    description: str
    hubspot_defined: bool


class NotFoundError(Exception):
    """Exception to indicate a resource was not found (404)."""

    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} {resource_id} not found")


class HubSpotClient:
    """A client for interacting with the HubSpot API."""

    def __init__(
        self,
        tenant_id: str,
        access_token: str,
        auth_service: "HubspotAuthService",
    ):
        self.tenant_id = tenant_id
        self.access_token = access_token
        self.auth_service = auth_service
        self.api_client = HubSpot(access_token=access_token)

    async def _execute_with_retry[T](
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        max_retries: int = MAX_AUTH_RETRIES,
    ) -> T:
        """
        Execute an operation with authentication retry logic.

        Args:
            operation: The async callable to execute
            operation_name: Name of the operation for logging
            resource_type: Optional resource type for 404 handling
            resource_id: Optional resource ID for 404 handling
            max_retries: Maximum number of retry attempts

        Returns:
            The result of the operation

        Raises:
            NotFoundError: If resource not found (404)
            RateLimitedError: If rate limit exceeded (429)
            ApiException: For other API errors
        """
        retry_count = 0

        while retry_count <= max_retries:
            try:
                return await operation()

            except HUBSPOT_API_EXCEPTIONS as e:
                # Handle 404 - resource not found
                if e.status == 404:
                    if resource_type and resource_id:
                        raise NotFoundError(resource_type, resource_id)
                    raise

                # Handle rate limiting
                if e.status == 429:
                    error_details = self._parse_rate_limit_error(e)
                    logger.warning(f"HubSpot rate limit hit: {error_details}")
                    raise RateLimitedError(message=f"HubSpot rate limit: {error_details}")

                # Handle authentication errors with token refresh
                if e.status == 401 and retry_count < max_retries:
                    logger.warning(
                        f"HubSpot API returned 401 for {operation_name}, "
                        "refreshing token and retrying..."
                    )
                    await self._refresh_token_and_retry()
                    retry_count += 1
                elif e.status == 400:
                    error_details = self._parse_400_error(e)
                    error_message = f"HubSpot API error in {operation_name}: {error_details}"
                    logger.error(error_message)
                    raise Exception(error_message)
                else:
                    logger.error(f"HubSpot API error in {operation_name}: {e}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected error in {operation_name}: {e}")
                raise

        raise Exception(f"Failed to complete {operation_name} after {max_retries} retries")

    @rate_limited(max_retries=5, base_delay=5)
    async def _search(
        self,
        operation: Callable[[HubSpotSearchReq], HubSpotSearchRes[Any]],
        operation_name: str,
        search_options: HubSpotSearchOptions,
        limit: int,
        after: int | None = None,
    ) -> AsyncGenerator[HubSpotSearchRes[Any]]:
        def _search_factory(
            search_request: HubSpotSearchReq,
        ) -> Callable[[], Awaitable[HubSpotSearchRes[Any]]]:
            async def _bound_do_search() -> HubSpotSearchRes[Any]:
                return operation(search_request)

            return _bound_do_search

        loop_after = after
        loop_search_options = search_options
        previous_res: HubSpotSearchRes[Any] | None = None

        while True:
            search_request = build_search_request(
                search_options=loop_search_options,
                after=loop_after,
                limit=limit,
            )

            bound_operation = _search_factory(search_request)
            res = await self._execute_with_retry(bound_operation, operation_name)

            # Nothing more returned, we are done!
            if not res.results:
                break

            # Remove objects that were present in the previous page to avoid duplicates with same
            # timestamp over page boundaries on window slide
            previous_ids: set[str] = {r.id for r in previous_res.results} if previous_res else set()
            res.results = [r for r in res.results if r.id not in previous_ids]

            # All objects in this page were duplicates (happens if more than "limit" objects with
            # the same timestamp down to the ms), Nothing to yield, continue to next page. In the
            # unlikely event there is more than a page of dupelicates we will end up yielding dupes
            # to consumers.
            if not res.results:
                loop_after = res.after
                previous_res = None
                continue

            yield res

            if res.after is None:
                break

            if res.after >= MAX_SEARCH_OFFSET - limit:
                logger.info(
                    "Hit HubSpot search pagination limit, sliding date window",
                    operation_name=operation_name,
                    limit=limit,
                    after=res.after,
                )

                last_result = res.results[-1]
                last_result_timestamp = datetime.fromisoformat(
                    cast(str, last_result.properties[loop_search_options["search_by"]])
                )

                # Bump timestamp by 1 ms (searching on exclusive LT end and respects 1 ms
                # granularity) to avoid skipping objects with the same timestamp hiding in the next
                # "page". This will result in at least 1 duplicate, so track previous page data and
                # remove duplicates.
                new_end = last_result_timestamp + timedelta(milliseconds=1)

                loop_search_options = HubSpotSearchOptions(
                    properties=loop_search_options["properties"],
                    date_filter=HubSpotSearchDateFilter(
                        start=loop_search_options["date_filter"]["start"],
                        end=new_end,
                    ),
                    search_by=loop_search_options["search_by"],
                )
                loop_after = None
            else:
                loop_after = res.after

            previous_res = res

    async def search_companies(
        self,
        search_options: HubSpotSearchOptions,
        after: int | None = None,
    ) -> AsyncGenerator[HubSpotSearchRes[Any]]:
        def _operation(req: HubSpotSearchReq) -> HubSpotSearchRes[Any]:
            raw_res = self.api_client.crm.companies.search_api.do_search(
                public_object_search_request=req
            )
            return self._parse_search_response(raw_res)

        async for page in self._search(
            operation=_operation,
            operation_name="search_companies",
            search_options=search_options,
            after=after,
            limit=MAX_COMPANIES_PER_PAGE,
        ):
            yield page

    @rate_limited(max_retries=5, base_delay=5)
    async def get_contact(self, contact_id: str, properties: list[str]) -> dict[str, Any] | None:
        """
        Get a single contact by ID with specified properties.
        """

        async def operation():
            api_response = self.api_client.crm.contacts.basic_api.get_by_id(
                contact_id=contact_id, properties=properties
            )
            return api_response

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_contact",
            resource_type="contact",
            resource_id=contact_id,
        )

    async def search_contacts(
        self,
        search_options: HubSpotSearchOptions,
        after: int | None = None,
    ) -> AsyncGenerator[HubSpotSearchRes[Any]]:
        def _operation(req: HubSpotSearchReq) -> HubSpotSearchRes[Any]:
            api_response = self.api_client.crm.contacts.search_api.do_search(
                public_object_search_request=req
            )
            return self._parse_search_response(api_response)

        async for page in self._search(
            operation=_operation,
            operation_name="search_contacts",
            search_options=search_options,
            after=after,
            limit=50,
        ):
            yield page

    @rate_limited(max_retries=5, base_delay=5)
    async def get_contacts(self, contact_ids: list[str], properties: list[str]) -> dict[str, Any]:
        """
        Get contacts using batch read.
        """
        request_body = {
            "inputs": [{"id": contact_id} for contact_id in contact_ids],
            "properties": properties,
        }

        async def operation():
            api_response = self.api_client.crm.contacts.batch_api.read(
                batch_read_input_simple_public_object_id=request_body,
                archived=False,
            )
            return api_response.results

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_contacts",
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_tickets(self, ticket_ids: list[str], properties: list[str]) -> dict[str, Any]:
        """
        Get tickets using batch read.
        """
        request_body = {
            "inputs": [{"id": ticket_id} for ticket_id in ticket_ids],
            "properties": properties,
        }

        async def operation():
            api_response = self.api_client.crm.tickets.batch_api.read(
                batch_read_input_simple_public_object_id=request_body,
                archived=False,
            )
            return api_response.results

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_tickets",
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_companies(self, company_ids: list[str], properties: list[str]) -> dict[str, Any]:
        """
        Get companies using batch read.
        """
        request_body = {
            "inputs": [{"id": company_id} for company_id in company_ids],
            "properties": properties,
        }

        async def operation():
            api_response = self.api_client.crm.companies.batch_api.read(
                batch_read_input_simple_public_object_id=request_body,
                archived=False,
            )
            return api_response.results

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_companies",
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_ticket(self, ticket_id: str, properties: list[str]) -> dict[str, Any] | None:
        """
        Get a single ticket by ID with specified properties.
        """

        async def operation():
            api_response = self.api_client.crm.tickets.basic_api.get_by_id(
                ticket_id=ticket_id, properties=properties
            )

            return api_response

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_ticket",
            resource_type="ticket",
            resource_id=ticket_id,
        )

    async def search_tickets(
        self,
        search_options: HubSpotSearchOptions,
        after: int | None = None,
    ) -> AsyncGenerator[HubSpotSearchRes[Any]]:
        def _operation(req: HubSpotSearchReq) -> HubSpotSearchRes[Any]:
            api_response = self.api_client.crm.tickets.search_api.do_search(
                public_object_search_request=req
            )
            return self._parse_search_response(api_response)

        async for page in self._search(
            operation=_operation,
            operation_name="search_tickets",
            search_options=search_options,
            after=after,
            limit=50,
        ):
            yield page

    @rate_limited(max_retries=5, base_delay=5)
    async def get_pipelines(self, object_type: str) -> list[Any]:
        """
        Fetch all deal pipelines from HubSpot.

        Returns:
            List of pipeline objects from the API
        """

        async def _operation():
            api_response = self.api_client.crm.pipelines.pipelines_api.get_all(
                object_type=object_type
            )
            return api_response.results

        return await self._execute_with_retry(_operation, f"get_{object_type}_pipelines")

    async def search_deals(
        self,
        search_options: HubSpotSearchOptions,
        after: int | None = None,
    ) -> AsyncGenerator[HubSpotSearchRes[Any]]:
        def _operation(req: HubSpotSearchReq) -> HubSpotSearchRes[Any]:
            api_response = self.api_client.crm.deals.search_api.do_search(
                public_object_search_request=req
            )
            return self._parse_search_response(api_response)

        async for page in self._search(
            operation=_operation,
            operation_name="search_deals",
            search_options=search_options,
            after=after,
            limit=50,
        ):
            yield page

    @rate_limited(max_retries=5, base_delay=5)
    async def get_company_associations(
        self, object_type: str, deal_ids: list[str]
    ) -> dict[str, list[str]]:
        """
        Get company associations for a batch of deals.

        Args:
            deal_ids: List of deal IDs to get associations for

        Returns:
            Dictionary mapping deal ID to list of associated company IDs
        """
        if not deal_ids:
            return {}

        # Chunk deal_ids into batches of 900
        batch_size = 900
        all_associations = {}

        for i in range(0, len(deal_ids), batch_size):
            batch_ids = deal_ids[i : i + batch_size]

            async def _operation(batch_ids=batch_ids):
                request_body = {"inputs": [{"id": deal_id} for deal_id in batch_ids]}
                # Use the v4 associations API
                api_response = self.api_client.crm.associations.v4.batch_api.get_page(
                    from_object_type=object_type,
                    to_object_type="companies",
                    batch_input_public_fetch_associations_batch_request=request_body,
                )

                # Parse the response to extract deal -> company mappings
                associations = {}
                for result in api_response.results:
                    deal_id = str(result._from.id)
                    company_ids = [str(to.to_object_id) for to in result.to]
                    associations[deal_id] = company_ids

                logger.debug(f"Fetched associations for {len(associations)} deals in batch")
                return associations

            batch_associations = await self._execute_with_retry(
                _operation, "get_company_associations"
            )
            all_associations.update(batch_associations)

        logger.debug(f"Fetched associations for {len(all_associations)} deals total")
        return all_associations

    @rate_limited(max_retries=5, base_delay=5)
    async def get_company(self, company_id: str, properties: list[str]) -> dict[str, Any] | None:
        """
        Get a single company by ID with specified properties.

        Args:
            company_id: The HubSpot company ID
            properties: List of property names to fetch

        Returns:
            Company data dictionary or None if not found
        """

        async def operation():
            api_response = self.api_client.crm.companies.basic_api.get_by_id(
                company_id=company_id, properties=properties
            )
            return api_response

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_company",
            resource_type="company",
            resource_id=company_id,
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_properties(
        self, object_type: str, args: dict[str, Any] | None = None
    ) -> list[Any]:
        """
        Get properties for a given object type.
        """
        if args is None:
            args = {}

        async def operation():
            return self.api_client.crm.properties.core_api.get_all(object_type=object_type, **args)

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_properties",
            resource_type=object_type,
        )

    async def get_custom_properties(
        self, object_type: str, args: dict[str, Any] | None = None
    ) -> list[HubSpotProperty]:
        """
        Get custom properties for a given object type.
        """
        properties = await self.get_properties(object_type, args)
        return [
            self._convert_property_to_object(prop)
            for prop in properties.results
            if not bool(prop.hubspot_defined)
        ]

    def _convert_property_to_object(self, property: Any) -> HubSpotProperty:
        """
        Convert a property to a dictionary.
        """
        return HubSpotProperty(
            name=property.name,
            label=property.label,
            type=property.type,
            description=property.description,
            hubspot_defined=bool(property.hubspot_defined),
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_deals_activities(
        self, deal_ids: list[str], properties: list[str]
    ) -> dict[str, dict[str, list[Any]]]:
        """
        Get activities for a deals.
        """
        activity_types = ["emails", "meetings", "tasks", "communications", "calls"]
        results: dict[str, dict[str, list[Any]]] = {}

        # get the activities for each activity type
        for activity_type in activity_types:
            activity_type_ids = await self.get_deals_activities_by_type(deal_ids, activity_type)
            for activity in activity_type_ids:
                if activity["deal_id"] not in results:
                    results[activity["deal_id"]] = {}
                results[activity["deal_id"]][activity["to_object_type"]] = activity[
                    "associated_object_ids"
                ]

        for deal_id in results:
            results[deal_id] = await self.get_deal_activities(results[deal_id], properties)

        return results

    @rate_limited(max_retries=5, base_delay=5)
    async def get_deals_activities_by_type(
        self, deal_ids: list[str], to_object_type: str
    ) -> list[Any]:
        """
        Get activities for a deals by to object type.
        Batches deal IDs in groups of 900 to comply with API limits.
        """
        batch_size = 900
        all_results = []

        for i in range(0, len(deal_ids), batch_size):
            batch_ids = deal_ids[i : i + batch_size]

            async def operation(batch_ids=batch_ids):
                results = []

                batch_request_body = {
                    "inputs": [{"id": deal_id} for deal_id in batch_ids],
                }

                deals_associations_response = (
                    self.api_client.crm.associations.v4.batch_api.get_page(
                        from_object_type="deals",
                        to_object_type=to_object_type,
                        batch_input_public_fetch_associations_batch_request=batch_request_body,
                    )
                )
                deals_associations = deals_associations_response.to_dict()
                for deal_activity in deals_associations["results"]:
                    deal_id = deal_activity["_from"]["id"]
                    associated_object_ids = [to["to_object_id"] for to in deal_activity["to"]]
                    results.append(
                        {
                            "deal_id": deal_id,
                            "associated_object_ids": associated_object_ids,
                            "to_object_type": to_object_type,
                        }
                    )
                return results

            batch_results = await self._execute_with_retry(
                operation=operation,
                operation_name="get_deals_activities_by_type",
            )
            all_results.extend(batch_results)

        return all_results

    @rate_limited(max_retries=5, base_delay=5)
    async def get_deal_activities(
        self, deal_associations: dict[str, list[str]], properties: list[str]
    ) -> dict[str, list[Any]]:
        """
        Get activities for a deal.
        """

        hubspot_object_apis = {
            "notes": self.api_client.crm.objects.notes.batch_api.read,
            "meetings": self.api_client.crm.objects.meetings.batch_api.read,
            "emails": self.api_client.crm.objects.emails.batch_api.read,
            "tasks": self.api_client.crm.objects.tasks.batch_api.read,
            "communications": self.api_client.crm.objects.communications.batch_api.read,
            "calls": self.api_client.crm.objects.calls.batch_api.read,
        }

        results: dict[str, list[Any]] = {
            a: [] for a in deal_associations if a in hubspot_object_apis
        }

        # tune this for HubSpot rate limits
        sem = asyncio.Semaphore(5)

        async def fetch_chunk(association: str, ids_chunk: list[str]) -> None:
            async with sem:

                async def operation():
                    request_body = {
                        "inputs": [{"id": association_id} for association_id in ids_chunk],
                        "properties": properties,
                    }
                    # HubSpot SDK is sync; run it in a thread
                    response = await asyncio.to_thread(
                        hubspot_object_apis[association],
                        batch_read_input_simple_public_object_id=request_body,
                    )
                    response_data = response.to_dict()
                    response_results = response_data.get("results") or []
                    for item in response_results:
                        props = item.get("properties")
                        if not props:
                            continue

                        if props.get("hs_email_text") and props.get("hs_email_html"):
                            # if we have both, keep the text to reduce data size
                            del props["hs_email_html"]

                        if props.get("hs_email_html"):
                            props["hs_email_html"] = self._clean_html(props["hs_email_html"])

                        if props.get("hs_email_text"):
                            props["hs_email_text"] = self._clean_html(props["hs_email_text"])

                        if props.get("hs_meeting_body"):
                            props["hs_meeting_body"] = self._clean_html(props["hs_meeting_body"])

                        results[association].append(props)

                await self._execute_with_retry(
                    operation=operation,
                    operation_name=f"get_{association}_properties",
                )

        tasks: list[asyncio.Task[None]] = []
        for association, ids in deal_associations.items():
            if association not in hubspot_object_apis:
                continue
            for i in range(0, len(ids), 100):
                tasks.append(asyncio.create_task(fetch_chunk(association, ids[i : i + 100])))

        await asyncio.gather(*tasks)
        return results

    def _clean_html(self, html: str | None, max_length: int = 1000) -> str | None:
        """Clean HTML by removing scripts and styles."""
        text = html_to_text_bs4(html)
        if not text:
            return None

        # Remove remaining bits of quoted text often starting with ">"
        text = re.sub(r"^\s*(?:>\s?)+", "", text, flags=re.MULTILINE)
        cleaned_text = re.sub(r"\s+", " ", text).strip()
        return cleaned_text[:max_length]

    # get deals using batch read
    @rate_limited(max_retries=5, base_delay=5)
    async def get_deals(self, deal_ids: list[str], properties: list[str]) -> dict[str, Any]:
        """
        Get deals using batch read.
        """
        request_body = {
            "inputs": [{"id": deal_id} for deal_id in deal_ids],
            "properties": properties,
        }

        async def operation():
            api_response = self.api_client.crm.deals.batch_api.read(
                batch_read_input_simple_public_object_id=request_body,
                archived=False,
            )
            return api_response.results

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_deals",
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def get_deal(
        self, deal_id: str, properties: list[str], include_associations: bool = True
    ) -> dict[str, Any] | None:
        """
        Get a single deal by ID with specified properties and optionally associations.

        Args:
            deal_id: The HubSpot deal ID
            properties: List of property names to fetch
            include_associations: Whether to include company associations

        Returns:
            Deal data dictionary or None if not found
        """

        async def operation():
            params = {
                "properties": properties,
            }

            if include_associations:
                params["associations"] = ["companies"]

            # Use the basic API to get a single deal
            api_response = self.api_client.crm.deals.basic_api.get_by_id(deal_id=deal_id, **params)

            return api_response

        return await self._execute_with_retry(
            operation=operation,
            operation_name="get_deal",
            resource_type="deal",
            resource_id=deal_id,
        )

    @rate_limited(max_retries=5, base_delay=5)
    async def batch_read_companies(
        self, company_ids: list[str], filters: dict[str, Any] | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Batch read company data for a list of company IDs.
        Returns default properties including name without specifying any.

        Args:
            company_ids: List of company IDs to fetch
            filters: Optional filters dict containing:
                - archived: If False, exclude archived companies

        Returns:
            Dictionary mapping company ID to company data
        """
        if not company_ids:
            return {}

        # For batch read, archived is a separate parameter to the API call
        archived_param = None
        if filters and filters.get("archived") is not None:
            archived_param = filters["archived"]

        # Chunk company_ids into batches of 90
        batch_size = 90
        all_companies = {}

        for i in range(0, len(company_ids), batch_size):
            batch_ids = company_ids[i : i + batch_size]

            # Build batch read request - no properties needed per API behavior

            async def _operation(batch_ids=batch_ids):
                request_body = {"inputs": [{"id": company_id} for company_id in batch_ids]}
                # Use the batch read API
                if archived_param is not None:
                    api_response = self.api_client.crm.companies.batch_api.read(
                        batch_read_input_simple_public_object_id=request_body,
                        archived=archived_param,
                    )
                else:
                    api_response = self.api_client.crm.companies.batch_api.read(
                        batch_read_input_simple_public_object_id=request_body
                    )

                # Parse the response to extract company data
                companies = {}
                for result in api_response.results:
                    company_id = str(result.id)
                    company_data = self._serialize_datetime_fields(result.to_dict())
                    companies[company_id] = company_data

                logger.debug(f"Fetched {len(companies)} companies via batch read")
                return companies

            batch_companies = await self._execute_with_retry(_operation, "batch_read_companies")
            all_companies.update(batch_companies)

        logger.debug(f"Fetched {len(all_companies)} companies total")
        return all_companies

    async def _refresh_token_and_retry(self):
        """Refresh the access token and recreate the API client."""
        logger.info(f"Refreshing HubSpot token for tenant {self.tenant_id}")
        self.access_token = await self.auth_service.refresh_token(self.tenant_id)
        self.api_client = HubSpot(access_token=self.access_token)

    def _parse_400_error(self, api_exception: HubspotApiException) -> str:
        """Extract detailed error message from 400 response."""
        error_details = f"{api_exception.reason}"
        if api_exception.body:
            try:
                body_dict = json.loads(api_exception.body)
                message = body_dict.get("message", "")
                status = body_dict.get("status", "")
                error_details = f"{message} (Status: {status})"
            except (json.JSONDecodeError, AttributeError):
                pass
        return error_details

    def _parse_rate_limit_error(self, api_exception: HubspotApiException) -> str:
        """Extract detailed error message from rate limit response."""
        error_details = f"{api_exception.reason}"
        if api_exception.body:
            try:
                body_dict = json.loads(api_exception.body)
                error_msg = body_dict.get("message", "")
                policy_name = body_dict.get("policyName", "")
                error_details = f"{error_msg} (Policy: {policy_name})" if policy_name else error_msg
            except (json.JSONDecodeError, AttributeError):
                pass
        return error_details

    def _parse_search_response(self, api_response: Any) -> HubSpotSearchRes[Any]:
        """Extract results and next cursor from API response."""
        next_cursor = None
        if (
            hasattr(api_response, "paging")
            and hasattr(api_response.paging, "next")
            and hasattr(api_response.paging.next, "after")
        ):
            next_cursor = api_response.paging.next.after

        logger.debug(f"Fetched {len(api_response.results)} objects from HubSpot")

        return HubSpotSearchRes(results=api_response.results, after=next_cursor)

    def _serialize_datetime_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert datetime objects to ISO format strings in a dictionary."""
        # Convert top-level datetime objects
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()

        # Also convert properties dict values if present
        if "properties" in data and isinstance(data["properties"], dict):
            for key, value in data["properties"].items():
                if isinstance(value, datetime):
                    data["properties"][key] = value.isoformat()

        return data
