"""Google Drive client utilities."""

import re


def sanitize_google_api_error(error: Exception) -> str:
    """Sanitize Google API HttpError messages for New Relic grouping.

    Google API HttpError exceptions include full URLs with variable file IDs,
    which prevents New Relic from grouping similar errors together. This function
    extracts the essential error information (status code, error type, reason)
    while removing variable identifiers.

    Args:
        error: The exception to sanitize (typically googleapiclient.errors.HttpError)

    Returns:
        Sanitized error message suitable for grouping

    Examples:
        Input:  "<HttpError 403 when requesting https://www.googleapis.com/drive/v3/files/ABC123/permissions..."
        Output: "HttpError 403: insufficientFilePermissions (drive API)"

        Input:  "<HttpError 404 when requesting https://www.googleapis.com/gmail/v1/users/me/messages/XYZ..."
        Output: "HttpError 404: notFound (gmail API)"
    """
    error_str = str(error)

    # Extract HTTP status code
    status_match = re.search(r"HttpError (\d+)", error_str)
    status_code = status_match.group(1) if status_match else "unknown"

    # Extract API name from URL (drive, gmail, admin, etc.)
    api_match = re.search(r"googleapis\.com/(\w+)/", error_str)
    api_name = api_match.group(1) if api_match else "google-api"

    # Extract error reason from the Details section
    reason_match = re.search(r"'reason': '(\w+)'", error_str)
    reason = reason_match.group(1) if reason_match else "unknown"

    # Build standardized error message
    return f"HttpError {status_code}: {reason} ({api_name} API)"
