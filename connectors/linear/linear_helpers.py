"""
Shared utility functions for Linear operations.
"""

import logging
from datetime import datetime
from typing import Any

from connectors.base.doc_ids import get_linear_doc_id
from connectors.linear.linear_issue_document import LinearIssueDocument

logger = logging.getLogger(__name__)


def get_user_display_name(user_data: dict[str, Any]) -> str:
    """Extract the best display name for a user from Linear user data.

    Args:
        user_data: User data dictionary from Linear API

    Returns:
        Display name, preferring displayName over name, defaulting to 'Unknown'
    """
    if not user_data:
        return "Unknown"

    # Prefer displayName over name
    return user_data.get("displayName") or user_data.get("name") or "Unknown"


def is_system_activity(actor_name: str, actor_id: str) -> bool:
    """Check if an activity is from a system actor and should be filtered out.

    Args:
        actor_name: Name of the actor
        actor_id: ID of the actor

    Returns:
        True if activity should be filtered out (is system), False otherwise
    """
    # Filter out system actors
    return (
        actor_name.lower() == "system"
        or actor_id.lower() == "system"
        or actor_name.lower() == "unknown"
    )


def format_linear_timestamp(timestamp: str) -> str:
    """Format Linear timestamp to readable format.

    Args:
        timestamp: ISO format timestamp string

    Returns:
        Formatted timestamp string (assuming UTC)
    """
    if not timestamp:
        return ""

    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp


def create_base_activity(
    activity_type: str,
    actor_name: str,
    actor_id: str,
    timestamp: str,
    issue_id: str,
    issue_title: str,
    team_id: str,
    team_name: str,
    activity_id: str,
) -> dict[str, Any]:
    """Create a base activity dictionary with common fields.

    Args:
        activity_type: Type of activity (e.g., 'issue_created', 'comment')
        actor_name: Name of the actor
        actor_id: ID of the actor
        timestamp: Activity timestamp
        issue_id: Issue ID
        issue_title: Issue title
        team_id: Team ID
        team_name: Team name
        activity_id: Unique activity identifier

    Returns:
        Dictionary with base activity fields
    """
    return {
        "activity_type": activity_type,
        "actor": actor_name,
        "actor_id": actor_id,
        "timestamp": timestamp,
        "formatted_time": format_linear_timestamp(timestamp),
        "issue_id": issue_id,
        "issue_title": issue_title,
        "team_id": team_id,
        "team_name": team_name,
        "activity_id": activity_id,
        "parent_id": "",
        "comment_body": "",
        "comment_id": "",
        "old_status": "",
        "new_status": "",
        "assignee": "",
        "priority": "",
        "label": "",
    }


def create_issue_created_activity(
    creator_data: dict[str, Any],
    timestamp: str,
    issue_id: str,
    issue_title: str,
    team_id: str,
    team_name: str,
) -> dict[str, Any]:
    """Create an issue creation activity.

    Args:
        creator_data: Creator information dictionary
        timestamp: Creation timestamp
        issue_id: Issue ID
        issue_title: Issue title
        team_id: Team ID
        team_name: Team name

    Returns:
        Issue creation activity dictionary
    """
    creator_name = get_user_display_name(creator_data)
    creator_id = creator_data.get("id", "")
    activity_id = f"issue_created_{issue_id}_{timestamp}"

    return create_base_activity(
        "issue_created",
        creator_name,
        creator_id,
        timestamp,
        issue_id,
        issue_title,
        team_id,
        team_name,
        activity_id,
    )


def create_comment_activity(
    comment_data: dict[str, Any], issue_id: str, issue_title: str, team_id: str, team_name: str
) -> dict[str, Any]:
    """Create a comment activity.

    Args:
        comment_data: Comment information dictionary
        issue_id: Issue ID
        issue_title: Issue title
        team_id: Team ID
        team_name: Team name

    Returns:
        Comment activity dictionary
    """
    timestamp = comment_data.get("createdAt", "")
    user = comment_data.get("user") or {}

    user_name = get_user_display_name(user)
    user_id = user.get("id", "") if user else ""
    comment_id = comment_data.get("id", "")

    # For API comments, use comment_{id}_{timestamp}, for webhooks use just comment_id
    activity_id = f"comment_{comment_id}_{timestamp}" if timestamp else comment_id

    activity = create_base_activity(
        "comment",
        user_name,
        user_id,
        timestamp,
        issue_id,
        issue_title,
        team_id,
        team_name,
        activity_id,
    )

    parent_data = comment_data.get("parent")
    if parent_data and isinstance(parent_data, dict):
        parent_id = parent_data.get("id", "")
    else:
        parent_id = comment_data.get("parentId", "")

    # Add comment-specific fields
    activity.update(
        {
            "comment_body": comment_data.get("body", ""),
            "comment_id": comment_id,
            "parent_id": parent_id,
        }
    )

    return activity


def extract_labels_from_issue_data(labels_data: Any) -> list[str]:
    """Extract label names from issue labels data.

    Args:
        labels_data: Labels data from Linear API (various formats)

    Returns:
        List of label names
    """
    labels: list[str] = []

    if not labels_data:
        return labels

    # API format: {'nodes': [{'name': 'label1'}, ...]}
    if isinstance(labels_data, dict) and "nodes" in labels_data:
        for label in labels_data.get("nodes", []):
            if isinstance(label, dict) and "name" in label:
                labels.append(label["name"])
    # Webhook format: [{'name': 'label1'}, ...]
    elif isinstance(labels_data, list):
        for label in labels_data:
            if isinstance(label, dict) and "name" in label:
                labels.append(label["name"])

    return labels


def extract_priority_from_issue_data(issue_data: dict[str, Any]) -> str:
    """Extract priority string from issue data.

    Args:
        issue_data: Issue data dictionary

    Returns:
        Priority string
    """
    # Try webhook format first (priorityLabel)
    priority_name = issue_data.get("priorityLabel", "")
    if priority_name:
        return priority_name

    # Try API format (priority number)
    priority_data = issue_data.get("priority", 0)
    if isinstance(priority_data, int):
        priority_map = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
        return priority_map.get(priority_data, "Unknown")

    # Fallback to string conversion
    return str(priority_data) if priority_data else ""


def extract_assignee_from_issue_data(issue_data: dict[str, Any]) -> str:
    """Extract assignee name from issue data.

    Args:
        issue_data: Issue data dictionary

    Returns:
        Assignee name string
    """
    assignee_data = issue_data.get("assignee") or {}
    if not assignee_data:
        return ""

    return get_user_display_name(assignee_data)


def normalize_user_names_in_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize user names across activities to ensure consistency.

    For each unique actor_id, uses the best available display name (preferring displayName over name)
    and applies it consistently to all activities by that user.

    Args:
        activities: List of activity dictionaries with actor and actor_id fields

    Returns:
        List of activities with normalized actor names
    """
    if not activities:
        return activities

    user_name_map: dict[str, str] = {}

    for activity in activities:
        actor_id = activity.get("actor_id", "")
        actor_name = activity.get("actor", "")

        if not actor_id or not actor_name:
            continue

        if actor_id not in user_name_map or len(actor_name) > len(user_name_map[actor_id]):
            user_name_map[actor_id] = actor_name

    normalized_activities = []
    for activity in activities:
        activity_copy = activity.copy()
        actor_id = activity_copy.get("actor_id", "")

        if actor_id and actor_id in user_name_map:
            activity_copy["actor"] = user_name_map[actor_id]

        normalized_activities.append(activity_copy)

    return normalized_activities


def create_linear_document_data(
    issue_id: str, issue_data: dict[str, Any], activities: list[dict[str, Any]]
) -> dict[str, Any]:
    """Create the standard document data structure for Linear issues.

    Args:
        issue_id: Issue ID
        issue_data: Issue data from API or webhook
        activities: List of activity dictionaries

    Returns:
        Document data dictionary
    """
    team_data = issue_data.get("team") or {}
    team_id = team_data.get("id", "") if team_data else ""
    team_name = team_data.get("name", "") if team_data else ""

    # Normalize user names for consistency within the document
    normalized_activities = normalize_user_names_in_activities(activities)

    return {
        "issue_id": issue_id,
        "issue_identifier": issue_data.get("identifier", ""),
        "issue_title": issue_data.get("title", ""),
        "issue_url": issue_data.get("url", ""),
        "issue_description": issue_data.get("description", ""),
        "team_id": team_id,
        "team_name": team_name,
        "status": issue_data.get("state", {}).get("name", "") if issue_data.get("state") else "",
        "priority": extract_priority_from_issue_data(issue_data),
        "assignee": extract_assignee_from_issue_data(issue_data),
        "labels": extract_labels_from_issue_data(issue_data.get("labels")),
        "activities": sorted(normalized_activities, key=lambda x: x.get("timestamp", "")),
    }


def create_linear_document(
    issue_id: str, document_data: dict[str, Any], source_updated_at: datetime
) -> LinearIssueDocument:
    """Create a LinearIssueDocument with standard ID format.

    Args:
        issue_id: Issue ID
        document_data: Document data dictionary
        source_updated_at: Source update timestamp

    Returns:
        LinearIssueDocument instance
    """
    document_id = get_linear_doc_id(issue_id)
    return LinearIssueDocument(
        id=document_id,
        raw_data=document_data,
        source_updated_at=source_updated_at,
        permission_policy="tenant",
        permission_allowed_tokens=None,
    )
