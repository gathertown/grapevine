"""AWS Systems Manager Parameter Store client for secure parameter management."""

import os
import time
from typing import Any

from botocore.exceptions import ClientError

from src.clients.aws_base import AWSBaseClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_kms_key_id() -> str:
    """Get KMS key ID from environment variable."""
    key_id = os.environ.get("KMS_KEY_ID")
    if not key_id:
        raise RuntimeError("No KMS key ID found. Set KMS_KEY_ID environment variable.")
    return key_id


class SSMClient(AWSBaseClient):
    """Client for AWS Systems Manager Parameter Store operations.

    This client only supports SecureString parameters with KMS encryption.
    """

    def __init__(self, region_name: str | None = None):
        """Initialize SSM client.

        Args:
            region_name: AWS region name, defaults to config value
        """
        super().__init__("ssm", region_name)
        # Cache stores (value, timestamp) tuples for TTL support
        self._parameter_cache: dict[str, tuple[Any, float]] = {}

    async def get_parameters(
        self,
        parameter_names: list[str],
        decrypt: bool = True,
        use_cache: bool = True,
    ) -> dict[str, str | None]:
        """Get multiple parameter values from SSM Parameter Store in a single call.

        This is more efficient than calling get_parameter() multiple times as it makes
        only one API call to fetch all parameters.

        Args:
            parameter_names: List of parameter names to retrieve
            decrypt: Whether to decrypt SecureString parameters
            use_cache: Whether to use cached values

        Returns:
            Dictionary mapping parameter names to their values (None if not found)
        """
        if not parameter_names:
            return {}

        result: dict[str, str | None] = {}
        uncached_names: list[str] = []

        # Check cache first if enabled
        if use_cache:
            for name in parameter_names:
                cache_key = f"{name}:{decrypt}"
                if cache_key in self._parameter_cache:
                    cached_value, cached_time = self._parameter_cache[cache_key]
                    result[name] = cached_value
                    logger.debug(f"Retrieved parameter {name} from cache")
                else:
                    uncached_names.append(name)
        else:
            uncached_names = parameter_names

        # Fetch uncached parameters from SSM
        if uncached_names:
            try:
                response = self.client.get_parameters(Names=uncached_names, WithDecryption=decrypt)

                # Process found parameters
                for param in response.get("Parameters", []):
                    name = param["Name"]
                    value = param["Value"]
                    result[name] = value

                    # Cache the value if caching is enabled
                    if use_cache:
                        cache_key = f"{name}:{decrypt}"
                        self._parameter_cache[cache_key] = (value, time.time())
                        logger.debug(f"Cached parameter {name}")

                # Mark not found parameters as None
                for name in response.get("InvalidParameters", []):
                    result[name] = None
                    logger.debug(f"Parameter {name} not found in SSM")

                # Ensure all requested parameters are in result
                for name in uncached_names:
                    if name not in result:
                        result[name] = None

                logger.debug(
                    f"Retrieved {len(response.get('Parameters', []))} parameters from SSM "
                    f"({len(response.get('InvalidParameters', []))} not found)"
                )

            except ClientError as e:
                self.handle_aws_error(e, f"get_parameters({len(uncached_names)} names)")
                # Return None for all uncached parameters on error
                for name in uncached_names:
                    result[name] = None
            except Exception as e:
                self.handle_aws_error(e, f"get_parameters({len(uncached_names)} names)")
                # Return None for all uncached parameters on error
                for name in uncached_names:
                    result[name] = None

        return result

    async def get_parameter(
        self,
        parameter_name: str,
        decrypt: bool = True,
        use_cache: bool = True,
        ttl_seconds: int | None = None,
    ) -> str | None:
        """Get parameter value from SSM Parameter Store.

        Args:
            parameter_name: Name of the parameter to retrieve
            decrypt: Whether to decrypt SecureString parameters
            use_cache: Whether to use cached values
            ttl_seconds: Optional TTL in seconds for cached values (None = no expiration)

        Returns:
            Parameter value or None if not found
        """
        # Check cache first if enabled
        cache_key = f"{parameter_name}:{decrypt}"
        if use_cache and cache_key in self._parameter_cache:
            cached_value, cached_time = self._parameter_cache[cache_key]

            # Check if cache entry has expired
            if ttl_seconds is None or (time.time() - cached_time) < ttl_seconds:
                logger.debug(f"Retrieved parameter {parameter_name} from cache")
                return cached_value
            else:
                logger.debug(f"Cache expired for parameter {parameter_name}, fetching fresh value")
                del self._parameter_cache[cache_key]

        try:
            response = self.client.get_parameter(Name=parameter_name, WithDecryption=decrypt)

            value = response["Parameter"]["Value"]

            # Cache the value with timestamp if caching is enabled
            if use_cache:
                self._parameter_cache[cache_key] = (value, time.time())
                logger.debug(
                    f"Cached parameter {parameter_name}"
                    + (f" with {ttl_seconds}s TTL" if ttl_seconds else "")
                )

            logger.debug(f"Retrieved parameter {parameter_name} from SSM")
            return value

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ParameterNotFound":
                logger.warning(f"Parameter {parameter_name} not found in SSM")
                return None
            else:
                self.handle_aws_error(e, f"get_parameter({parameter_name})")
                return None
        except Exception as e:
            self.handle_aws_error(e, f"get_parameter({parameter_name})")
            return None

    async def put_parameter(
        self,
        parameter_name: str,
        value: str,
        description: str | None = None,
        overwrite: bool = True,
    ) -> None:
        """Store parameter in SSM Parameter Store as SecureString.

        Args:
            parameter_name: Name of the parameter
            value: Parameter value to store
            description: Optional description for the parameter
            overwrite: Whether to overwrite existing parameters

        Raises:
            Exception: If the parameter cannot be stored
        """
        try:
            put_params = {
                "Name": parameter_name,
                "Value": value,
                "Type": "SecureString",
                "Tier": "Advanced",
                "Overwrite": overwrite,
                "KeyId": _get_kms_key_id(),
            }

            if description:
                put_params["Description"] = description

            self.client.put_parameter(**put_params)

            # Invalidate cache for this parameter
            cache_keys_to_remove = [
                key for key in self._parameter_cache if key.startswith(f"{parameter_name}:")
            ]
            for key in cache_keys_to_remove:
                del self._parameter_cache[key]

            logger.info(f"Successfully stored parameter {parameter_name}")

        except Exception as e:
            self.handle_aws_error(e, f"put_parameter({parameter_name})")

    async def get_signing_secret(self, tenant_id: str, source_type: str) -> str | None:
        """Get signing secret for a specific tenant and source.

        Args:
            tenant_id: Tenant identifier
            source_type: Source type (github, slack, linear, notion)

        Returns:
            Signing secret or None if not found
        """
        parameter_name = f"/{tenant_id}/signing-secret/{source_type}"
        return await self.get_parameter(parameter_name, decrypt=True)

    async def store_signing_secret(self, tenant_id: str, source_type: str, secret: str) -> None:
        """Store signing secret for a specific tenant and source.

        Args:
            tenant_id: Tenant identifier
            source_type: Source type (github, slack, linear, notion)
            secret: Signing secret to store

        Raises:
            Exception: If the secret cannot be stored
        """
        parameter_name = f"/{tenant_id}/signing-secret/{source_type}"
        description = f"Webhook signing secret for {tenant_id} {source_type}"

        return await self.put_parameter(
            parameter_name=parameter_name,
            value=secret,
            description=description,
            overwrite=True,
        )

    async def get_api_key(self, tenant_id: str, key_name: str) -> str | None:
        """Get API key for a specific tenant and key name.

        Args:
            tenant_id: Tenant identifier
            key_name: API key name/identifier

        Returns:
            API key value or None if not found
        """
        parameter_name = f"/{tenant_id}/api-key/{key_name}"
        return await self.get_parameter(parameter_name, decrypt=True)

    async def store_api_key(self, tenant_id: str, key_name: str, key_value: str) -> None:
        """Store API key for a specific tenant and key name.

        Args:
            tenant_id: Tenant identifier
            key_name: API key name/identifier
            key_value: API key value to store

        Raises:
            Exception: If the secret cannot be stored
        """
        parameter_name = f"/{tenant_id}/api-key/{key_name}"
        description = f"API key {key_name} for {tenant_id}"

        return await self.put_parameter(
            parameter_name=parameter_name,
            value=key_value,
            description=description,
            overwrite=True,
        )

    async def get_db_credential(self, tenant_id: str, credential_name: str) -> str | None:
        """Get database credential for a specific tenant and credential name.

        Args:
            tenant_id: Tenant identifier
            credential_name: Database credential name/identifier

        Returns:
            Database credential value or None if not found
        """
        parameter_name = f"/{tenant_id}/db-credential/{credential_name}"
        return await self.get_parameter(parameter_name, decrypt=True)

    async def store_db_credential(
        self, tenant_id: str, credential_name: str, credential_value: str
    ) -> None:
        """Store database credential for a specific tenant and credential name.

        Args:
            tenant_id: Tenant identifier
            credential_name: Database credential name/identifier
            credential_value: Database credential value to store

        Raises:
            Exception: If the secret cannot be stored
        """
        parameter_name = f"/{tenant_id}/db-credential/{credential_name}"
        description = f"Database credential {credential_name} for {tenant_id}"

        return await self.put_parameter(
            parameter_name=parameter_name,
            value=credential_value,
            description=description,
            overwrite=True,
        )

    def clear_cache(self) -> None:
        """Clear the parameter cache."""
        self._parameter_cache.clear()
        logger.debug("Cleared SSM parameter cache")

    def get_cache_size(self) -> int:
        """Get current cache size."""
        return len(self._parameter_cache)

    # Configuration getter helper methods
    # ---------------------------------

    async def get_github_token(self, tenant_id: str) -> str | None:
        """Get GitHub token for a specific tenant."""
        return await self.get_api_key(tenant_id, "GITHUB_TOKEN")

    async def get_github_webhook_secret(self, tenant_id: str) -> str | None:
        """Get GitHub webhook secret for a specific tenant."""
        return await self.get_signing_secret(tenant_id, "github")

    async def get_github_app_token(self, tenant_id: str) -> str | None:
        """Get GitHub App token for a specific tenant."""
        return await self.get_api_key(tenant_id, "GITHUB_APP_TOKEN")

    async def get_slack_token(self, tenant_id: str) -> str | None:
        """Get Slack bot token for a specific tenant."""
        return await self.get_api_key(tenant_id, "SLACK_BOT_TOKEN")

    async def get_slack_signing_secret(self, tenant_id: str) -> str | None:
        """Get Slack signing secret for webhook verification for a specific tenant."""
        return await self.get_signing_secret(tenant_id, "slack")

    async def get_notion_signing_secret(self, tenant_id: str) -> str | None:
        """Get Notion webhook signing secret for a specific tenant."""
        return await self.get_signing_secret(tenant_id, "notion")

    async def get_openai_api_key(self, tenant_id: str) -> str | None:
        """Get OpenAI API key for a specific tenant."""
        return await self.get_api_key(tenant_id, "OPENAI_API_KEY")

    async def get_notion_token(self, tenant_id: str) -> str | None:
        """Get Notion token for a specific tenant."""
        return await self.get_api_key(tenant_id, "NOTION_TOKEN")

    async def get_linear_token(self, tenant_id: str) -> str | None:
        """Get Linear token for a specific tenant.

        This tries to get OAuth access token first, then falls back to API key for backwards compatibility.
        """
        # Try OAuth access token first
        access_token = await self.get_api_key(tenant_id, "LINEAR_ACCESS_TOKEN")
        if access_token:
            return access_token

        # Fall back to API key (legacy)
        return await self.get_api_key(tenant_id, "LINEAR_API_KEY")

    async def get_linear_access_token(self, tenant_id: str) -> str | None:
        """Get Linear OAuth access token for a specific tenant."""
        return await self.get_api_key(tenant_id, "LINEAR_ACCESS_TOKEN")

    async def get_linear_refresh_token(self, tenant_id: str) -> str | None:
        """Get Linear OAuth refresh token for a specific tenant."""
        return await self.get_api_key(tenant_id, "LINEAR_REFRESH_TOKEN")

    async def store_linear_access_token(self, tenant_id: str, token: str) -> None:
        """Store Linear OAuth access token for a specific tenant."""
        return await self.store_api_key(tenant_id, "LINEAR_ACCESS_TOKEN", token)

    async def store_linear_refresh_token(self, tenant_id: str, token: str) -> None:
        """Store Linear OAuth refresh token for a specific tenant."""
        return await self.store_api_key(tenant_id, "LINEAR_REFRESH_TOKEN", token)

    async def get_google_drive_webhook_channel(self, tenant_id: str) -> str | None:
        """Get Google Drive webhook channel info for a specific tenant."""
        return await self.get_api_key(tenant_id, "GOOGLE_DRIVE_WEBHOOK_CHANNEL")

    async def store_google_drive_webhook_channel(self, tenant_id: str, channel_json: str) -> None:
        """Store Google Drive webhook channel info for a specific tenant."""
        return await self.store_api_key(tenant_id, "GOOGLE_DRIVE_WEBHOOK_CHANNEL", channel_json)

    async def get_google_drive_admin_email(self, tenant_id: str) -> str | None:
        """Get Google Drive admin email for domain-wide delegation."""
        return await self.get_api_key(tenant_id, "GOOGLE_DRIVE_ADMIN_EMAIL")

    async def get_google_email_admin_email(self, tenant_id: str) -> str | None:
        """Get Google Email admin email for domain-wide delegation."""
        return await self.get_api_key(tenant_id, "GOOGLE_EMAIL_ADMIN_EMAIL")

    async def store_google_drive_admin_email(self, tenant_id: str, admin_email: str) -> None:
        """Store Google Drive admin email for domain-wide delegation."""
        return await self.store_api_key(tenant_id, "GOOGLE_DRIVE_ADMIN_EMAIL", admin_email)

    async def get_google_drive_service_account(self, tenant_id: str) -> str | None:
        """Get Google Drive service account JSON for a tenant."""
        return await self.get_api_key(tenant_id, "GOOGLE_DRIVE_SERVICE_ACCOUNT")

    async def get_google_email_service_account(self, tenant_id: str) -> str | None:
        """Get Google Email service account JSON for a tenant."""
        return await self.get_api_key(tenant_id, "GOOGLE_EMAIL_SERVICE_ACCOUNT")

    async def get_google_email_pub_sub_topic(self, tenant_id: str) -> str | None:
        """Get Google Email Pub/Sub topic for a tenant."""
        return await self.get_api_key(tenant_id, "GOOGLE_EMAIL_PUB_SUB_TOPIC")

    async def store_google_drive_service_account(
        self, tenant_id: str, service_account_json: str
    ) -> None:
        """Store Google Drive service account JSON for a tenant."""
        return await self.store_api_key(
            tenant_id, "GOOGLE_DRIVE_SERVICE_ACCOUNT", service_account_json
        )

    async def get_salesforce_refresh_token(self, tenant_id: str) -> str | None:
        """Get Salesforce refresh token for a specific tenant."""
        return await self.get_api_key(tenant_id, "SALESFORCE_REFRESH_TOKEN")

    async def get_hubspot_access_token(self, tenant_id: str) -> str | None:
        """Get HubSpot access token for a specific tenant. These tokens expire in 30 minutes."""
        parameter_name = f"/{tenant_id}/api-key/HUBSPOT_ACCESS_TOKEN"
        return await self.get_parameter(
            parameter_name,
            decrypt=True,
            use_cache=False,
        )

    async def get_hubspot_refresh_token(self, tenant_id: str) -> str | None:
        """Get HubSpot refresh token for a specific tenant. These tokens expire in 30 minutes."""
        parameter_name = f"/{tenant_id}/api-key/HUBSPOT_REFRESH_TOKEN"
        return await self.get_parameter(
            parameter_name,
            decrypt=True,
            use_cache=False,
        )

    async def get_gong_access_token(self, tenant_id: str) -> str | None:
        """Get Gong API access token for a specific tenant."""
        return await self.get_api_key(tenant_id, "GONG_ACCESS_TOKEN")

    async def get_gong_refresh_token(self, tenant_id: str) -> str | None:
        """Get Gong API refresh token for a specific tenant."""
        return await self.get_api_key(tenant_id, "GONG_REFRESH_TOKEN")

    async def get_gong_webhook_public_key(self, tenant_id: str) -> str | None:
        """Get Gong webhook public key for a specific tenant."""
        return await self.get_api_key(tenant_id, "GONG_WEBHOOK_PUBLIC_KEY")

    async def get_jira_system_oauth_token(self, tenant_id: str) -> str | None:
        """Get Jira system OAuth token for a specific tenant.

        Note: OAuth tokens are cached for 1 hour to balance performance and freshness.
        """
        parameter_name = f"/{tenant_id}/api-key/JIRA_SYSTEM_OAUTH_TOKEN"
        return await self.get_parameter(
            parameter_name, decrypt=True, use_cache=True, ttl_seconds=3600
        )

    async def get_confluence_system_oauth_token(self, tenant_id: str) -> str | None:
        """Get Confluence system OAuth token for a specific tenant.

        Note: OAuth tokens are cached for 1 hour to balance performance and freshness.
        """
        parameter_name = f"/{tenant_id}/api-key/CONFLUENCE_SYSTEM_OAUTH_TOKEN"
        return await self.get_parameter(
            parameter_name, decrypt=True, use_cache=True, ttl_seconds=3600
        )

    async def get_gather_api_key(self, tenant_id: str) -> str | None:
        """Get Gather API key for a specific tenant."""
        return await self.get_api_key(tenant_id, "GATHER_API_KEY")

    async def get_gather_signing_secret(self, tenant_id: str) -> str | None:
        """Get Gather webhook signing secret for a specific tenant."""
        return await self.get_signing_secret(tenant_id, "gather")

    async def get_trello_token(self, tenant_id: str) -> str | None:
        """Get Trello access token for a specific tenant."""
        return await self.get_api_key(tenant_id, "TRELLO_ACCESS_TOKEN")

    async def store_trello_token(self, tenant_id: str, token: str) -> None:
        """Store Trello access token for a specific tenant."""
        return await self.store_api_key(tenant_id, "TRELLO_ACCESS_TOKEN", token)

    async def get_trello_signing_secret(self, tenant_id: str) -> str | None:
        """Get Trello webhook signing secret for a specific tenant."""
        return await self.get_signing_secret(tenant_id, "trello")

    async def get_zendesk_token_payload(self, tenant_id: str) -> str | None:
        """Get Zendesk API token payload for a specific tenant."""
        return await self.get_api_key(tenant_id, "ZENDESK_TOKEN_PAYLOAD")

    async def store_zendesk_token_payload(self, tenant_id: str, token_payload_json: str) -> None:
        """Store Zendesk API token payload for a specific tenant."""
        return await self.store_api_key(tenant_id, "ZENDESK_TOKEN_PAYLOAD", token_payload_json)

    async def get_asana_oauth_token_payload(self, tenant_id: str) -> str | None:
        """Get Asana OAuth token payload for a specific tenant."""
        return await self.get_api_key(tenant_id, "ASANA_OAUTH_TOKEN_PAYLOAD")

    async def store_asana_oauth_token_payload(
        self, tenant_id: str, token_payload_json: str
    ) -> None:
        """Store Asana OAuth token payload for a specific tenant."""
        return await self.store_api_key(tenant_id, "ASANA_OAUTH_TOKEN_PAYLOAD", token_payload_json)

    async def get_asana_service_account_token(self, tenant_id: str) -> str | None:
        """Get Asana service account token for a specific tenant."""
        return await self.get_api_key(tenant_id, "ASANA_SERVICE_ACCOUNT_TOKEN")

    async def get_fireflies_api_key(self, tenant_id: str) -> str | None:
        """Get Fireflies API key for a specific tenant."""
        return await self.get_api_key(tenant_id, "FIREFLIES_API_KEY")

    async def get_clickup_oauth_token(self, tenant_id: str) -> str | None:
        """Get Clickup OAuth token for a specific tenant."""
        return await self.get_api_key(tenant_id, "CLICKUP_OAUTH_TOKEN")

    async def get_pylon_api_key(self, tenant_id: str) -> str | None:
        """Get Pylon API key for a specific tenant."""
        return await self.get_api_key(tenant_id, "PYLON_API_KEY")

    async def delete_parameter(self, parameter_name: str) -> bool:
        """Delete a parameter from SSM Parameter Store.

        Args:
            parameter_name: Name of the parameter to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.client.delete_parameter(Name=parameter_name)

            # Invalidate cache for this parameter
            cache_keys_to_remove = [
                key for key in self._parameter_cache if key.startswith(f"{parameter_name}:")
            ]
            for key in cache_keys_to_remove:
                del self._parameter_cache[key]

            logger.info(f"Deleted parameter {parameter_name}")
            return True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ParameterNotFound":
                logger.warning(f"Parameter {parameter_name} not found, nothing to delete")
                return True  # Consider it a success if it doesn't exist
            else:
                self.handle_aws_error(e, f"delete_parameter({parameter_name})")
                return False
        except Exception as e:
            self.handle_aws_error(e, f"delete_parameter({parameter_name})")
            return False

    async def get_parameters_by_path(
        self,
        path: str,
        decrypt: bool = True,
        recursive: bool = True,
    ) -> list[str]:
        """Get all parameter names under a path.

        Args:
            path: Path prefix to search (e.g., "/{tenant_id}")
            decrypt: Whether to decrypt SecureString parameters
            recursive: Whether to search recursively

        Returns:
            List of parameter names found under the path
        """
        parameter_names: list[str] = []

        try:
            paginator = self.client.get_paginator("get_parameters_by_path")

            for page in paginator.paginate(
                Path=path,
                Recursive=recursive,
                WithDecryption=decrypt,
            ):
                for param in page.get("Parameters", []):
                    parameter_names.append(param["Name"])

            logger.debug(f"Found {len(parameter_names)} parameters under path {path}")
            return parameter_names

        except ClientError as e:
            self.handle_aws_error(e, f"get_parameters_by_path({path})")
            return []
        except Exception as e:
            self.handle_aws_error(e, f"get_parameters_by_path({path})")
            return []

    async def delete_parameters_by_path(self, path: str) -> tuple[int, int]:
        """Delete all parameters under a path.

        This is useful for cleaning up all tenant-specific parameters during tenant deletion.

        Args:
            path: Path prefix to delete (e.g., "/{tenant_id}")

        Returns:
            Tuple of (deleted_count, failed_count)
        """
        # First, get all parameters under the path
        parameter_names = await self.get_parameters_by_path(path, decrypt=False)

        if not parameter_names:
            logger.info(f"No parameters found under path {path}")
            return (0, 0)

        deleted_count = 0
        failed_count = 0

        # Delete parameters in batches of 10 (SSM limit for delete_parameters)
        batch_size = 10
        for i in range(0, len(parameter_names), batch_size):
            batch = parameter_names[i : i + batch_size]

            try:
                response = self.client.delete_parameters(Names=batch)

                deleted_names = response.get("DeletedParameters", [])
                deleted_count += len(deleted_names)

                invalid_names = response.get("InvalidParameters", [])
                failed_count += len(invalid_names)

                if invalid_names:
                    logger.warning(f"Failed to delete parameters: {invalid_names}")

                # Invalidate cache for deleted parameters
                for name in deleted_names:
                    cache_keys_to_remove = [
                        key for key in self._parameter_cache if key.startswith(f"{name}:")
                    ]
                    for key in cache_keys_to_remove:
                        del self._parameter_cache[key]

            except ClientError as e:
                self.handle_aws_error(e, f"delete_parameters(batch of {len(batch)})")
                failed_count += len(batch)
            except Exception as e:
                self.handle_aws_error(e, f"delete_parameters(batch of {len(batch)})")
                failed_count += len(batch)

        logger.info(f"Deleted {deleted_count} parameters under path {path} ({failed_count} failed)")
        return (deleted_count, failed_count)

    async def delete_tenant_parameters(self, tenant_id: str) -> tuple[int, int]:
        """Delete all SSM parameters for a specific tenant.

        This is a convenience method that deletes all parameters under /{tenant_id}/.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Tuple of (deleted_count, failed_count)
        """
        return await self.delete_parameters_by_path(f"/{tenant_id}")
