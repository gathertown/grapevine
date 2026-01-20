"""Base AWS client for shared boto3 session management and configuration."""

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AWSBaseClient:
    """Base class for AWS service clients with shared configuration and session management."""

    def __init__(self, service_name: str, region_name: str | None = None):
        """Initialize AWS base client.

        Args:
            service_name: AWS service name (e.g., 'ssm', 'sqs', 'sts')
            region_name: AWS region name, defaults to config value
        """
        self.service_name = service_name
        self.region_name = region_name or get_config_value("AWS_REGION", "us-east-1")
        self._client = None
        self._session = None

    @property
    def session(self) -> boto3.Session:
        """Get or create boto3 session."""
        if not self._session:
            if get_config_value("AWS_ACCESS_KEY_ID") and get_config_value("AWS_SECRET_ACCESS_KEY"):
                session_kwargs = {
                    "region_name": self.region_name,
                    "aws_access_key_id": get_config_value("AWS_ACCESS_KEY_ID"),
                    "aws_secret_access_key": get_config_value("AWS_SECRET_ACCESS_KEY"),
                }

                # Include session token if available (matches JavaScript pattern)
                session_token = get_config_value("AWS_SESSION_TOKEN")
                if session_token:
                    session_kwargs["aws_session_token"] = session_token
                    logger.info("Including AWS session token in credentials")

                self._session = boto3.Session(**session_kwargs)
            else:
                self._session = boto3.Session(region_name=self.region_name)
        return self._session

    @property
    def client(self) -> BaseClient:
        """Get or create boto3 client for the service."""
        if not self._client:
            # Check for LocalStack endpoint override
            endpoint_url = get_config_value("AWS_ENDPOINT_URL", None)
            if endpoint_url:
                logger.debug(f"Using AWS endpoint URL: {endpoint_url}")
                self._client = self.session.client(self.service_name, endpoint_url=endpoint_url)
            else:
                self._client = self.session.client(self.service_name)
        return self._client

    def handle_aws_error(self, error: Exception, operation: str) -> None:
        """Handle AWS-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed

        Raises:
            The original exception after logging
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            error_message = error.response.get("Error", {}).get("Message", str(error))
            logger.error(
                f"AWS {self.service_name} {operation} failed - {error_code}: {error_message}"
            )
        elif isinstance(error, BotoCoreError):
            logger.error(f"AWS {self.service_name} {operation} failed - BotoCore error: {error}")
        else:
            logger.error(f"AWS {self.service_name} {operation} failed - Unexpected error: {error}")

        raise error

    def get_account_id(self) -> str:
        """Get AWS account ID from STS."""
        try:
            sts_client = self.session.client("sts")
            response = sts_client.get_caller_identity()
            return response["Account"]
        except Exception as e:
            self.handle_aws_error(e, "get_caller_identity")
            raise  # This will never be reached due to handle_aws_error raising
