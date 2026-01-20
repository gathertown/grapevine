"""
Centralized document ID generation functions.

This module contains helper functions to generate consistent document IDs
for all document types across the system. Each function takes the minimal
required parameters and returns a properly formatted document ID.
"""

import re


def get_notion_doc_id(page_id: str) -> str:
    return f"notion_page_{page_id}"


def get_github_pr_doc_id(repo_id: str, pr_number: int) -> str:
    return f"{repo_id}_pr_{pr_number}"


def get_github_file_doc_id(entity_id: str) -> str:
    return f"github_file_{entity_id}"


def get_linear_doc_id(issue_id: str) -> str:
    return f"issue_{issue_id}"


def get_slack_doc_id(channel_id: str, date: str) -> str:
    return f"{channel_id}_{date}"


def get_google_drive_doc_id(file_id: str) -> str:
    return f"google_drive_file_{file_id}"


def get_salesforce_doc_id(object_type: str, record_id: str) -> str:
    return f"salesforce_{object_type.lower()}_{record_id}"


def get_google_email_doc_id(message_id: str) -> str:
    return f"google_email_message_{message_id}"


def get_jira_doc_id(issue_id: str) -> str:
    return f"jira_issue_{issue_id}"


def get_hubspot_doc_id(object_type: str, record_id: str) -> str:
    return f"hubspot_{object_type}_{record_id}"


def get_confluence_page_doc_id(page_id: str) -> str:
    return f"confluence_page_{page_id}"


def get_confluence_space_doc_id(space_id: str) -> str:
    return f"confluence_space_{space_id}"


def get_gong_call_doc_id(call_id: str) -> str:
    return f"gong_call_{call_id}"


def parse_gong_call_entity_id(entity_id: str) -> str | None:
    """Extract call_id from Gong call entity_id.

    Args:
        entity_id: The entity ID (e.g., "gong_call_1234567")

    Returns:
        The call_id or None if the entity_id doesn't match the expected format
    """
    if entity_id.startswith("gong_call_"):
        return entity_id[len("gong_call_") :]
    return None


def get_trello_card_doc_id(card_id: str) -> str:
    return f"trello_card_{card_id}"


def get_trello_board_doc_id(board_id: str) -> str:
    return f"trello_board_{board_id}"


def get_gather_meeting_doc_id(meeting_id: str) -> str:
    return f"gather_meeting_{meeting_id}"


def get_attio_company_doc_id(record_id: str) -> str:
    return f"attio_company_{record_id}"


def get_attio_person_doc_id(record_id: str) -> str:
    return f"attio_person_{record_id}"


def get_attio_deal_doc_id(record_id: str) -> str:
    return f"attio_deal_{record_id}"


def get_gitlab_mr_doc_id(project_id: int, mr_iid: int) -> str:
    return f"gitlab_mr_{project_id}_{mr_iid}"


def get_gitlab_file_doc_id(entity_id: str) -> str:
    return f"gitlab_file_{entity_id}"


def get_figma_file_doc_id(file_key: str) -> str:
    return f"figma_file_{file_key}"


def get_figma_comment_doc_id(comment_id: str) -> str:
    return f"figma_comment_{comment_id}"


# --------


def is_valid_slack_doc_id(doc_id: str) -> bool:
    return bool(re.match(r"^[CD][A-Z0-9]+_\d{4}-\d{2}-\d{2}$", doc_id))


async def get_slack_channel_doc_ids(channel_id: str, conn) -> list[str]:
    """
    Find all document IDs for a given Slack channel.

    Uses metadata filtering to find all Slack documents that belong to the specified channel.
    This is more efficient and semantically correct than pattern matching on document IDs.

    Args:
        channel_id: The Slack channel ID
        conn: Database connection

    Returns:
        List of document IDs for the channel
    """
    # Query documents table using metadata->>'channel_id' filter
    rows = await conn.fetch(
        """SELECT DISTINCT id FROM documents
           WHERE source = 'slack' AND metadata->>'channel_id' = $1""",
        channel_id,
    )

    return [row["id"] for row in rows]
