"""
Reference ID generation functions for document references.

This module provides functions to generate consistent reference IDs
for different document types from their component parts.

Reference IDs are similar to document IDs, but used specifically for the
document references system. We need to be able to generate a given document's
reference ID from both text source formats (e.g. URLs, ENG-123) as well as from
the document itself. The former isn't always possible with document IDs.
"""


def get_linear_issue_reference_id(issue_id: str) -> str:
    """Generate a reference ID for a Linear issue.

    Args:
        issue_id: The Linear issue identifier (e.g., "ENG-123")
    """
    return f"r_linear_issue_{issue_id.lower()}"


def get_github_pr_reference_id(owner: str, repo: str, pr_number: str) -> str:
    """Generate a reference ID for a GitHub pull request.

    Args:
        owner: GitHub repository owner/organization
        repo: GitHub repository name
        pr_number: Pull request number
    """
    return f"r_github_pr_{owner}_{repo}_{pr_number}"


def get_github_file_reference_id(owner: str, repo: str, file_path: str) -> str:
    """Generate a reference ID for a GitHub file.

    Args:
        owner: GitHub repository owner/organization
        repo: GitHub repository name
        file_path: File path within the repository
    """
    return f"r_github_file_{owner}_{repo}_{file_path.rstrip()}"


def get_notion_page_reference_id(page_uuid: str) -> str:
    """Generate a reference ID for a Notion page.

    Args:
        page_uuid: Notion page UUID (with or without dashes)
    """
    normalized_uuid = normalize_notion_uuid(page_uuid)
    return f"r_notion_page_{normalized_uuid}"


def get_google_drive_file_reference_id(file_id: str) -> str:
    """Generate a reference ID for a Google Drive file.

    Args:
        file_id: Google Drive file ID (alphanumeric string)
    """
    return f"r_gdrive_file_{file_id}"


def get_salesforce_reference_id(object_type: str, record_id: str) -> str:
    """Generate a reference ID for a Salesforce record.

    Args:
        object_type: Salesforce object type (e.g., "Account", "Contact")
        record_id: Salesforce record ID (15 or 18 character)
    """
    return f"r_salesforce_{object_type.lower()}_{record_id}"


def get_jira_issue_reference_id(issue_id: str) -> str:
    """Generate a reference ID for a Jira issue.

    Args:
        issue_id: The Jira internal issue ID (numeric string format, e.g., "10218")
    """
    return f"r_jira_issue_{issue_id}"


def get_confluence_page_reference_id(page_id: str) -> str:
    """Generate a reference ID for a Confluence page.

    Args:
        page_id: The Confluence page ID (numeric string format, e.g., "12345")
    """
    return f"r_confluence_page_{page_id}"


def get_gong_call_reference_id(call_id: str) -> str:
    """Generate a reference ID for a Gong call."""

    return f"r_gong_call_{call_id}"


def get_gitlab_mr_reference_id(project_path: str, mr_iid: int | str) -> str:
    """Generate a reference ID for a GitLab merge request.

    Args:
        project_path: GitLab project path (e.g., "group/project")
        mr_iid: Merge request internal ID
    """
    # Replace slashes with underscores for the reference ID
    normalized_path = project_path.replace("/", "_")
    return f"r_gitlab_mr_{normalized_path}_{mr_iid}"


def get_gitlab_file_reference_id(project_path: str, file_path: str) -> str:
    """Generate a reference ID for a GitLab file.

    Args:
        project_path: GitLab project path (e.g., "group/project")
        file_path: File path within the repository
    """
    # Replace slashes with underscores for the project path
    normalized_path = project_path.replace("/", "_")
    return f"r_gitlab_file_{normalized_path}_{file_path.rstrip()}"


def normalize_notion_uuid(uuid_str: str) -> str:
    """Normalize a Notion UUID to standard format with dashes.

    Args:
        uuid_str: UUID string with or without dashes

    Returns:
        Normalized UUID in format "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    """
    # Remove any existing dashes
    clean_uuid = uuid_str.replace("-", "")

    # Add dashes in standard positions
    if len(clean_uuid) == 32:
        return f"{clean_uuid[:8]}-{clean_uuid[8:12]}-{clean_uuid[12:16]}-{clean_uuid[16:20]}-{clean_uuid[20:32]}".lower()

    return uuid_str.lower()
