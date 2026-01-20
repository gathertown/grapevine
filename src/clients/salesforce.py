"""
Salesforce REST API client for OAuth-based operations.
"""

import asyncio
import csv
import json
from io import StringIO
from typing import Any
from urllib.parse import quote

import aiohttp

from connectors.salesforce import SUPPORTED_SALESFORCE_OBJECTS
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class SalesforceClient:
    """A client for interacting with the Salesforce REST API."""

    def __init__(self, instance_url: str, org_id: str, access_token: str):
        self.instance_url = instance_url.rstrip("/")
        self.org_id = org_id
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    @classmethod
    async def from_refresh_token(
        cls, instance_url: str, org_id: str, refresh_token: str, client_id: str, client_secret: str
    ) -> "SalesforceClient":
        """Create client using refresh token flow."""
        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("All OAuth parameters are required for refresh token flow")

        # Exchange refresh token for access token
        token_url = f"{instance_url.rstrip('/')}/services/oauth2/token"
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        async with (
            aiohttp.ClientSession() as session,
            session.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as token_response,
        ):
            if token_response.status != 200:
                response_text = await token_response.text()
                logger.error(f"Token refresh failed: {token_response.status} - {response_text}")
                token_response.raise_for_status()

            token_data = await token_response.json()
            access_token = token_data["access_token"]

        return cls(instance_url, org_id, access_token)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    @rate_limited(max_retries=3, base_delay=1)
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make a request to the Salesforce API with rate limiting."""
        url = f"{self.instance_url}/services/data/v65.0{endpoint}"
        session = await self._get_session()

        try:
            async with session.request(method, url, **kwargs) as response:
                # Check for rate limiting
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Salesforce rate limit hit, retrying after {retry_after}s")
                    raise RateLimitedError(retry_after=retry_after)

                response.raise_for_status()

                try:
                    return await response.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    # Handle empty or non-JSON responses
                    text = await response.text()
                    if text.strip():
                        logger.warning(f"Salesforce API returned non-JSON response: {text[:200]}")
                    return {}

        except RateLimitedError:
            raise
        except aiohttp.ClientError as e:
            logger.error(f"Salesforce API request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Salesforce API request failed: {e}")
            raise

    async def bulk_query_soql(self, soql: str) -> list[dict[str, Any]]:
        """Execute a SOQL query and return all records using the Bulk API."""
        bulk_query_url = "/jobs/query"
        bulk_query_data = {
            "operation": "query",
            "query": soql,
        }
        bulk_query_response = await self._make_request("POST", bulk_query_url, json=bulk_query_data)
        job_id = bulk_query_response.get("id")

        if not job_id:
            raise ValueError(f"Failed to create bulk query job: {bulk_query_response}")

        logger.info(f"Created bulk query job {job_id}")

        max_wait = 600  # 10 minutes
        poll_interval = 2  # seconds
        elapsed = 0

        while elapsed < max_wait:
            job_status_url = f"/jobs/query/{job_id}"
            status_response = await self._make_request("GET", job_status_url)
            state = status_response.get("state")

            logger.info(f"Bulk query job {job_id} state: {state}")

            if state == "JobComplete":
                break
            elif state in ["Failed", "Aborted"]:
                error_msg = status_response.get("errorMessage", "Unknown error")
                raise RuntimeError(f"Bulk query job failed: {error_msg}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if elapsed >= max_wait:
            raise TimeoutError(f"Bulk query job {job_id} did not complete within {max_wait}s")

        results_url = f"/jobs/query/{job_id}/results"
        session = await self._get_session()
        url = f"{self.instance_url}/services/data/v65.0{results_url}"

        all_records = []
        async with session.get(url) as response:
            response.raise_for_status()

            csv_text = await response.text()

            reader = csv.DictReader(StringIO(csv_text))
            all_records = [dict(row) for row in reader]

        logger.info(f"Retrieved {len(all_records)} records from bulk query job {job_id}")
        return all_records

    async def query_soql(self, soql: str) -> list[dict[str, Any]]:
        """Execute a SOQL query and return all records."""
        records = []
        query_url = f"/query?q={quote(soql)}"

        while query_url:
            result = await self._make_request("GET", query_url)
            if "records" in result:
                # Remove Salesforce metadata from records
                clean_records = []
                for record in result["records"]:
                    clean_record = {k: v for k, v in record.items() if k != "attributes"}
                    clean_records.append(clean_record)
                records.extend(clean_records)

            # Handle pagination
            if result.get("done", True):
                break

            next_records_url = result.get("nextRecordsUrl")
            if next_records_url:
                # Convert full URL to relative path
                logger.info(f"Found next records URL in query response: {next_records_url}")
                query_url = next_records_url.split("/services/data/v65.0")[-1]
            else:
                break

        return records

    async def get_records_by_ids(
        self,
        sobject_type: SUPPORTED_SALESFORCE_OBJECTS,
        record_ids: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get multiple records by their IDs in a single API call using SOQL WHERE IN.

        Args:
            sobject_type: SObject type (e.g., 'Account', 'Contact')
            record_ids: List of record IDs to retrieve
            fields: List of fields to retrieve (gets all fields if None)
        """
        if not record_ids:
            return []

        # Chunk record_ids to balance API efficiency with query limits
        # The relevant Salesforce limit here is 4k chars per WHERE clause:
        # https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/salesforce_soql_sosl.pdf
        # This is not ideal for latency / request usage, but it's sufficient for now. In the longer term,
        # we can consider other approaches like using the Bulk API or Composite API.
        chunk_size = 200  # up to 18 chars per ID -> ~3.6k chars
        all_records = []

        for i in range(0, len(record_ids), chunk_size):
            chunk_ids = record_ids[i : i + chunk_size]

            # Build SOQL query with WHERE IN clause
            fields_str = ", ".join(fields) if fields else "FIELDS(ALL)"

            # Format IDs for SOQL IN clause
            ids_str = "'" + "', '".join(chunk_ids) + "'"
            soql = f"SELECT {fields_str} FROM {sobject_type} WHERE Id IN ({ids_str})"

            chunk_records = await self.query_soql(soql)
            all_records.extend(chunk_records)

        return all_records

    async def get_all_object_ids(self, sobject_type: SUPPORTED_SALESFORCE_OBJECTS) -> list[str]:
        """
        Get all record IDs for a specific SObject type, up to 50k records
        (Salesforce governor limit for records returned by one SOQL query)
        """
        soql = f"SELECT Id FROM {sobject_type}"
        results = await self.bulk_query_soql(soql)
        return [record["Id"] for record in results if "Id" in record]

    async def get_updated_object_ids(
        self, sobject_type: SUPPORTED_SALESFORCE_OBJECTS, last_modified_date: str
    ) -> list[str]:
        """
        Get all record IDs for a specific SObject type that have been updated since a given date.
        """
        soql = f"SELECT Id FROM {sobject_type} WHERE LastModifiedDate > {last_modified_date}"
        records = await self.query_soql(soql)
        return [record["Id"] for record in records if "Id" in record]
