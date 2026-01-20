"""GitHub App client for generating installation tokens and handling app authentication."""

import hashlib
import hmac
import time
from typing import Any

import jwt
import requests
from pydantic import BaseModel

from src.utils.config import get_config_value
from src.utils.logging import get_logger
from src.utils.rate_limiter import rate_limited

logger = get_logger(__name__)


class GitHubInstallationTokenResponse(BaseModel):
    """Response from GitHub App installation token creation."""

    token: str
    expires_at: str
    permissions: dict[str, str]
    repository_selection: str


class GitHubAppClient:
    """Client for GitHub App authentication and token management."""

    def __init__(self):
        """Initialize GitHub App client.

        Raises:
            ValueError: If required credentials don't exist in the environment
        """
        self.app_id: int = get_config_value("GITHUB_APP_ID")
        self.private_key: str = get_config_value("GITHUB_APP_PRIVATE_KEY")
        self.webhook_secret: str = get_config_value("GITHUB_APP_WEBHOOK_SECRET")

        if not self.app_id or not isinstance(self.app_id, int):
            raise ValueError("GitHub App ID is required (GITHUB_APP_ID env var)")
        if not self.private_key:
            raise ValueError("GitHub App private key is required (GITHUB_APP_PRIVATE_KEY env var)")
        if not self.webhook_secret:
            raise ValueError(
                "GitHub App webhook secret is required (GITHUB_APP_WEBHOOK_SECRET env var)"
            )

        # Validate private key format
        self._validate_private_key(self.private_key)

    def _validate_private_key(self, private_key: str) -> None:
        """Validate that the private key is in correct PEM format.

        Args:
            private_key: The private key string to validate

        Raises:
            ValueError: If the private key is invalid
        """
        if not private_key.strip().startswith("-----BEGIN"):
            raise ValueError("Private key must be in PEM format starting with '-----BEGIN'")

        # Test JWT generation to ensure key is valid
        try:
            test_payload = {
                "iat": int(time.time()),
                "exp": int(time.time()) + 60,
                "iss": self.app_id,
            }
            jwt.encode(test_payload, private_key, algorithm="RS256")
        except Exception as e:
            raise ValueError(f"Invalid private key format: {e}")

    def generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication.

        Returns:
            JWT token valid for 10 minutes
        """
        try:
            now = int(time.time())
            payload = {
                "iat": now - 60,  # Issued 1 minute in the past to allow for clock skew
                "exp": now + (10 * 60),  # Expires in 10 minutes (max allowed by GitHub)
                "iss": self.app_id,
            }

            return jwt.encode(payload, self.private_key, algorithm="RS256")
        except Exception as e:
            logger.error(f"Failed to generate GitHub App JWT: {e}")
            raise

    @rate_limited()
    def get_installation_token(self, installation_id: int) -> str:
        """Generate installation access token for a specific installation.

        Returns:
            Installation access token (valid for 1 hour)
        """
        try:
            app_jwt = self.generate_jwt()

            headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
            response = requests.post(url, headers=headers, timeout=30)

            if response.status_code != 201:
                logger.error(
                    f"Failed to create installation token: {response.status_code}. Response: {response.text}"
                )
                response.raise_for_status()

            token_data = response.json()
            logger.debug(f"Generated installation token for installation {installation_id}")

            return token_data["token"]

        except Exception as e:
            logger.error(f"Failed to generate installation token: {e}")
            raise

    @rate_limited()
    def get_installation_info(self, installation_id: int) -> dict[str, Any]:
        """Get information about a specific installation.

        Returns:
            Installation details including account info and repository access
        """
        try:
            app_jwt = self.generate_jwt()

            headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            url = f"https://api.github.com/app/installations/{installation_id}"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                logger.error(
                    f"Failed to get installation info: {response.status_code}. Response: {response.text}"
                )
                response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get installation info: {e}")
            raise

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify that a webhook payload came from GitHub.

        Args:
            payload: Raw webhook payload bytes
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid, False otherwise
        """
        if not signature or not signature.startswith("sha256="):
            logger.warning("Invalid signature format")
            return False

        try:
            # Remove 'sha256=' prefix
            expected_signature = signature[7:]

            # Generate HMAC signature
            mac = hmac.new(self.webhook_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

            # Compare signatures securely
            return hmac.compare_digest(mac, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    @rate_limited()
    def list_installations(self) -> list[dict[str, Any]]:
        """List all installations of this GitHub App."""
        try:
            app_jwt = self.generate_jwt()

            headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            url = "https://api.github.com/app/installations"
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                logger.error(
                    f"Failed to list installations: {response.status_code}. Response: {response.text}"
                )
                response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to list installations: {e}")
            raise


# Global instance for easy access
_github_app_client: GitHubAppClient | None = None


def get_github_app_client() -> GitHubAppClient:
    """Get singleton GitHub App client instance."""
    global _github_app_client

    if _github_app_client is None:
        _github_app_client = GitHubAppClient()

    return _github_app_client
