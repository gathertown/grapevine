import re

from src.permissions.models import PermissionAudience, PermissionPolicy
from src.utils.logging import get_logger

logger = get_logger(__name__)


def make_email_permission_token(email: str) -> str:
    """Make an email address as a permission token.

    Args:
        email: User email address

    Returns:
        Permission token in format 'e:email@domain.com'
    """
    return f"e:{email}"


def _looks_like_email(email: str) -> bool:
    """Basic check if a string looks roughly like an email address."""
    return bool(re.fullmatch(r"^\S+@\S+\.\S+$", email))


def _is_valid_email_permission_token(token: str) -> bool:
    is_email_permission_token = token.startswith("e:")

    if is_email_permission_token:
        email_part = token[2:]
        if not _looks_like_email(email_part):
            logger.warning(f"Email Permission token: {token} does not look like email.")

    return is_email_permission_token


def is_valid_permission_token(token: str) -> bool:
    """
    Validate a permission allowed token.
    Currently only email-based tokens are supported, which start with 'e:'.
    """
    return _is_valid_email_permission_token(token)


def can_access_document(
    permission_policy: PermissionPolicy,
    permission_allowed_tokens: list[str] | None,
    permission_token: str,
) -> bool:
    """Check if a permission token can access a document.

    Args:
        permission_policy: Document policy ("tenant" or "private")
        permission_allowed_tokens: List of allowed permission tokens or None
        permission_token: User's permission token (e.g., "e:alice@gather.com")

    Returns:
        True if access is allowed
    """
    if permission_policy == "tenant":
        return True
    if permission_allowed_tokens is None:
        return False
    return permission_token in permission_allowed_tokens


def should_include_private_documents(
    permission_audience: PermissionAudience | None,
    permission_principal_token: str | None,
) -> bool:
    """Check if private documents should be included in search results.

    Permission filtering logic:
    - "private" audience + token: include private documents user has access to
    - "private" audience, no token: exclude private documents
    - "tenant" audience or None: exclude private documents (regardless of token)

    Args:
        permission_audience: Audience policy ("tenant" or "private")
        permission_principal_token: User's permission token (e.g., "e:alice@gather.com")

    Returns:
        True if private documents should be included in results
    """
    return permission_audience == "private" and permission_principal_token is not None
