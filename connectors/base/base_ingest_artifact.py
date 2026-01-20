"""Base ingest artifact models and entity types."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ArtifactEntity(str, Enum):
    """Valid artifact entity types in the system."""

    # Notion entities
    NOTION_PAGE = "notion_page"
    NOTION_USER = "notion_user"
    NOTION_DATABASE = "notion_database"

    # Slack entities
    SLACK_CHANNEL = "slack_channel"
    SLACK_USER = "slack_user"
    SLACK_MESSAGE = "slack_message"
    SLACK_TEAM = "slack_team"

    # GitHub entities
    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"
    GITHUB_REPO = "github_repo"
    GITHUB_USER = "github_user"
    GITHUB_FILE = "github_file"

    # Linear entities
    LINEAR_ISSUE = "linear_issue"
    LINEAR_PROJECT = "linear_project"
    LINEAR_TEAM = "linear_team"

    # Jira entities
    JIRA_ISSUE = "jira_issue"
    JIRA_PROJECT = "jira_project"
    JIRA_USER = "jira_user"

    # Confluence entities
    CONFLUENCE_PAGE = "confluence_page"
    CONFLUENCE_SPACE = "confluence_space"

    # Google Drive entities
    GOOGLE_DRIVE_FILE = "google_drive_file"
    GOOGLE_DRIVE_USER = "google_drive_user"
    GOOGLE_DRIVE_SHARED_DRIVE = "google_drive_shared_drive"

    # Google Email entities
    GOOGLE_EMAIL_MESSAGE = "google_email_message"

    # Salesforce entities
    SALESFORCE_ACCOUNT = "salesforce_account"
    SALESFORCE_CONTACT = "salesforce_contact"
    SALESFORCE_OPPORTUNITY = "salesforce_opportunity"
    SALESFORCE_LEAD = "salesforce_lead"
    SALESFORCE_CASE = "salesforce_case"

    # HubSpot entities
    HUBSPOT_COMPANY = "hubspot_company"
    HUBSPOT_TICKET = "hubspot_ticket"
    HUBSPOT_DEAL = "hubspot_deal"
    HUBSPOT_DEAL_ACTIVITY = "hubspot_deal_activity"
    HUBSPOT_CONTACT = "hubspot_contact"

    # Custom collections
    CUSTOM_COLLECTION_ITEM = "custom_collection_item"

    # Gong entities
    GONG_USER = "gong_user"
    GONG_PERMISSION_PROFILE = "gong_permission_profile"
    GONG_PERMISSION_PROFILE_USER = "gong_permission_profile_user"
    GONG_LIBRARY_FOLDER = "gong_library_folder"
    GONG_LIBRARY_FOLDER_CONTENT = "gong_library_folder_content"
    GONG_CALL = "gong_call"
    GONG_CALL_TRANSCRIPT = "gong_call_transcript"
    GONG_CALL_USERS_ACCESS = "gong_call_users_access"

    # Gather entities
    GATHER_MEETING = "gather_meeting"
    GATHER_MEETING_MEMO = "gather_meeting_memo"
    GATHER_MEETING_TRANSCRIPT = "gather_meeting_transcript"
    GATHER_CHAT_MESSAGE = "gather_chat_message"

    # Trello entities
    TRELLO_WORKSPACE = "trello_workspace"
    TRELLO_BOARD = "trello_board"
    TRELLO_CARD = "trello_card"

    # Zendesk entities
    ZENDESK_TICKET = "zendesk_ticket"
    ZENDESK_TICKET_FIELD = "zendesk_ticket_field"
    ZENDESK_TICKET_AUDIT = "zendesk_ticket_audit"
    ZENDESK_CUSTOM_STATUS = "zendesk_custom_status"
    ZENDESK_BRAND = "zendesk_brand"
    ZENDESK_ORGANIZATION = "zendesk_organization"
    ZENDESK_GROUP = "zendesk_group"
    ZENDESK_USER = "zendesk_user"
    ZENDESK_TICKET_METRICS = "zendesk_ticket_metrics"
    ZENDESK_ARTICLE = "zendesk_article"
    ZENDESK_COMMENT = "zendesk_comment"
    ZENDESK_CATEGORY = "zendesk_category"
    ZENDESK_SECTION = "zendesk_section"

    # Asana entities
    ASANA_TASK = "asana_task"
    ASANA_STORY = "asana_story"
    ASANA_PROJECT_PERMISSIONS = "asana_project_permissions"
    ASANA_TEAM_PERMISSIONS = "asana_team_permissions"

    # Intercom entities
    INTERCOM_CONVERSATION = "intercom_conversation"
    INTERCOM_HELP_CENTER_ARTICLE = "intercom_help_center_article"
    INTERCOM_CONTACT = "intercom_contact"
    INTERCOM_COMPANY = "intercom_company"

    # Attio entities
    ATTIO_COMPANY = "attio_company"
    ATTIO_PERSON = "attio_person"
    ATTIO_DEAL = "attio_deal"
    ATTIO_NOTE = "attio_note"
    ATTIO_TASK = "attio_task"

    # Fireflies entities
    FIREFLIES_TRANSCRIPT = "fireflies_transcript"

    # GitLab entities
    GITLAB_MR = "gitlab_mr"
    GITLAB_FILE = "gitlab_file"

    # ClickUp entities
    CLICKUP_SPACE = "clickup_space"
    CLICKUP_LIST = "clickup_list"
    CLICKUP_TASK = "clickup_task"
    CLICKUP_COMMENT = "clickup_comment"
    CLICKUP_WORKSPACE = "clickup_workspace"

    # Custom Data entities
    CUSTOM_DATA_DOCUMENT = "custom_data_document"

    # Pylon entities
    PYLON_ISSUE = "pylon_issue"
    PYLON_MESSAGE = "pylon_message"
    PYLON_ACCOUNT = "pylon_account"
    PYLON_CONTACT = "pylon_contact"
    PYLON_USER = "pylon_user"
    PYLON_TEAM = "pylon_team"

    # Monday.com entities
    MONDAY_ITEM = "monday_item"

    # Pipedrive entities
    PIPEDRIVE_DEAL = "pipedrive_deal"
    PIPEDRIVE_PERSON = "pipedrive_person"
    PIPEDRIVE_ORGANIZATION = "pipedrive_organization"
    PIPEDRIVE_ACTIVITY = "pipedrive_activity"
    PIPEDRIVE_NOTE = "pipedrive_note"
    PIPEDRIVE_USER = "pipedrive_user"
    PIPEDRIVE_PRODUCT = "pipedrive_product"

    # Figma entities
    FIGMA_FILE = "figma_file"
    FIGMA_COMMENT = "figma_comment"

    # PostHog entities
    POSTHOG_DASHBOARD = "posthog_dashboard"
    POSTHOG_INSIGHT = "posthog_insight"
    POSTHOG_FEATURE_FLAG = "posthog_feature_flag"
    POSTHOG_ANNOTATION = "posthog_annotation"
    POSTHOG_EXPERIMENT = "posthog_experiment"
    POSTHOG_SURVEY = "posthog_survey"

    # Canva entities
    CANVA_DESIGN = "canva_design"

    # Teamwork entities
    TEAMWORK_TASK = "teamwork_task"
    TEAMWORK_PROJECT = "teamwork_project"
    TEAMWORK_USER = "teamwork_user"


class BaseIngestArtifact(BaseModel):
    """Base class for all ingest artifacts."""

    id: UUID = Field(default_factory=uuid4)
    entity: ArtifactEntity
    entity_id: str
    ingest_job_id: UUID
    content: dict[str, Any] | BaseModel
    metadata: dict[str, Any] | BaseModel
    source_updated_at: datetime
    indexed_at: datetime | None = None

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields."""
        data = super().model_dump(**kwargs)
        # Convert any BaseModel instances to dicts
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump()
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump()
        return data


# Entity ID generation functions
def get_github_pr_entity_id(*, repo_id: str, pr_number: int) -> str:
    """Generate entity ID for GitHub PR artifacts."""
    return f"{repo_id}_pr_{pr_number}"


def get_github_file_entity_id(*, organization: str, repository: str, file_path: str) -> str:
    """Generate entity ID for GitHub file artifacts."""
    return f"{organization}/{repository}/{file_path}"


def get_slack_message_entity_id(*, channel_id: str, ts: str) -> str:
    """Generate entity ID for Slack message artifacts."""
    return f"{channel_id}_{ts}"


def get_slack_channel_entity_id(*, channel_id: str) -> str:
    """Generate entity ID for Slack channel artifacts."""
    return channel_id


def get_slack_user_entity_id(*, user_id: str) -> str:
    """Generate entity ID for Slack user artifacts."""
    return user_id


def get_slack_team_entity_id(*, team_id: str) -> str:
    """Generate entity ID for Slack team artifacts."""
    return team_id


def get_notion_page_entity_id(*, page_id: str) -> str:
    """Generate entity ID for Notion page artifacts."""
    return page_id


def get_notion_user_entity_id(*, user_id: str) -> str:
    """Generate entity ID for Notion user artifacts."""
    return user_id


def get_linear_issue_entity_id(*, issue_id: str) -> str:
    """Generate entity ID for Linear issue artifacts."""
    return issue_id


def get_google_drive_file_entity_id(*, file_id: str) -> str:
    """Generate entity ID for Google Drive file artifacts."""
    return file_id


def get_google_drive_user_entity_id(*, user_id: str) -> str:
    """Generate entity ID for Google Drive user artifacts."""
    return user_id


def get_google_drive_shared_drive_entity_id(*, drive_id: str) -> str:
    """Generate entity ID for Google Drive shared drive artifacts."""
    return drive_id


def get_google_email_message_entity_id(*, message_id: str) -> str:
    """Generate entity ID for Google Email message artifacts."""
    return message_id


def get_salesforce_object_entity_id(*, record_id: str) -> str:
    """Generate entity ID for all Salesforce object artifacts."""
    return record_id


def get_hubspot_company_entity_id(*, company_id: str) -> str:
    """Generate entity ID for HubSpot company artifacts."""
    return company_id


def get_hubspot_deal_entity_id(*, deal_id: str) -> str:
    """Generate entity ID for HubSpot deal artifacts."""
    return deal_id


def get_hubspot_ticket_entity_id(*, ticket_id: str) -> str:
    """Generate entity ID for HubSpot ticket artifacts."""
    return ticket_id


def get_hubspot_contact_entity_id(*, contact_id: str) -> str:
    """Generate entity ID for HubSpot contact artifacts."""
    return contact_id


def get_jira_issue_entity_id(*, issue_id: str) -> str:
    """Generate entity ID for Jira issue artifacts."""
    return issue_id  # Use internal numeric ID, no transformation needed


def get_jira_user_entity_id(*, user_id: str) -> str:
    """Generate entity ID for Jira user artifacts."""
    return user_id  # Use Jira account ID, no transformation needed


def get_jira_project_entity_id(*, project_id: str) -> str:
    """Generate entity ID for Jira project artifacts."""
    return project_id  # Use internal project ID, no transformation needed


def get_confluence_page_entity_id(*, page_id: str) -> str:
    """Generate entity ID for Confluence page artifacts."""
    return page_id  # Use internal page ID, no transformation needed


def get_confluence_space_entity_id(*, space_id: str) -> str:
    """Generate entity ID for Confluence space artifacts."""
    return space_id  # Use internal space ID, no transformation needed


def get_custom_collection_item_entity_id(*, collection_name: str, item_id: str) -> str:
    """Generate entity ID for custom collection items.

    Format: {collection_name}::{item_id}
    Example: customer-feedback::feedback-001
    """
    return f"{collection_name}::{item_id}"


def get_gather_meeting_entity_id(*, meeting_id: str) -> str:
    """Generate entity ID for Gather meeting artifacts."""
    return meeting_id


def get_gather_meeting_memo_entity_id(*, meeting_id: str, memo_id: str) -> str:
    """Generate entity ID for Gather meeting memo artifacts."""
    return f"{meeting_id}_memo_{memo_id}"


def get_gather_meeting_transcript_entity_id(
    *, meeting_id: str, memo_id: str, transcript_id: str
) -> str:
    """Generate entity ID for Gather meeting transcript artifacts."""
    return f"{meeting_id}_memo_{memo_id}_transcript_{transcript_id}"


def get_gather_chat_message_entity_id(*, meeting_id: str, message_id: str) -> str:
    """Generate entity ID for Gather chat message artifacts."""
    return f"{meeting_id}_message_{message_id}"


def get_trello_workspace_entity_id(*, workspace_id: str) -> str:
    """Generate entity ID for Trello workspace/organization artifacts."""
    return workspace_id


def get_trello_board_entity_id(*, board_id: str) -> str:
    """Generate entity ID for Trello board artifacts."""
    return board_id


def get_trello_card_entity_id(*, card_id: str) -> str:
    """Generate entity ID for Trello card artifacts."""
    return card_id


def get_attio_company_entity_id(*, company_id: str) -> str:
    """Generate entity ID for Attio company artifacts."""
    return company_id


def get_attio_person_entity_id(*, person_id: str) -> str:
    """Generate entity ID for Attio person artifacts."""
    return person_id


def get_attio_deal_entity_id(*, deal_id: str) -> str:
    """Generate entity ID for Attio deal artifacts."""
    return deal_id


def get_attio_note_entity_id(*, note_id: str) -> str:
    """Generate entity ID for Attio note artifacts."""
    return note_id


def get_attio_task_entity_id(*, task_id: str) -> str:
    """Generate entity ID for Attio task artifacts."""
    return task_id


def get_custom_data_document_entity_id(*, slug: str, item_id: str) -> str:
    """Generate entity ID for custom data document artifacts.

    Format: {slug}::{item_id}
    Example: customer-feedback::doc-001
    """
    return f"{slug}::{item_id}"


def get_gitlab_mr_entity_id(*, project_id: int, mr_iid: int) -> str:
    """Generate entity ID for GitLab MR artifacts.

    Format: {project_id}_mr_{mr_iid}
    Example: 12345_mr_42
    """
    return f"{project_id}_mr_{mr_iid}"


def get_gitlab_file_entity_id(*, project_id: int, file_path: str) -> str:
    """Generate entity ID for GitLab file artifacts.

    Format: {project_id}/{file_path}
    Example: 12345/src/main.py
    """
    return f"{project_id}/{file_path}"


def get_pylon_issue_entity_id(*, issue_id: str) -> str:
    """Generate entity ID for Pylon issue artifacts."""
    return f"pylon_issue_{issue_id}"


def get_pylon_message_entity_id(*, message_id: str) -> str:
    """Generate entity ID for Pylon message artifacts."""
    return f"pylon_message_{message_id}"


def get_pylon_account_entity_id(*, account_id: str) -> str:
    """Generate entity ID for Pylon account artifacts."""
    return f"pylon_account_{account_id}"


def get_pylon_contact_entity_id(*, contact_id: str) -> str:
    """Generate entity ID for Pylon contact artifacts."""
    return f"pylon_contact_{contact_id}"


def get_pylon_user_entity_id(*, user_id: str) -> str:
    """Generate entity ID for Pylon user artifacts."""
    return f"pylon_user_{user_id}"


def get_pylon_team_entity_id(*, team_id: str) -> str:
    """Generate entity ID for Pylon team artifacts."""
    return f"pylon_team_{team_id}"


def get_monday_item_entity_id(*, item_id: int) -> str:
    """Generate entity ID for Monday.com item artifacts."""
    return f"monday_item_{item_id}"


def get_pipedrive_deal_entity_id(*, deal_id: int) -> str:
    """Generate entity ID for Pipedrive deal artifacts."""
    return f"pipedrive_deal_{deal_id}"


def get_pipedrive_person_entity_id(*, person_id: int) -> str:
    """Generate entity ID for Pipedrive person artifacts."""
    return f"pipedrive_person_{person_id}"


def get_pipedrive_organization_entity_id(*, org_id: int) -> str:
    """Generate entity ID for Pipedrive organization artifacts."""
    return f"pipedrive_organization_{org_id}"


def get_pipedrive_activity_entity_id(*, activity_id: int) -> str:
    """Generate entity ID for Pipedrive activity artifacts."""
    return f"pipedrive_activity_{activity_id}"


def get_pipedrive_note_entity_id(*, note_id: int) -> str:
    """Generate entity ID for Pipedrive note artifacts."""
    return f"pipedrive_note_{note_id}"


def get_pipedrive_user_entity_id(*, user_id: int) -> str:
    """Generate entity ID for Pipedrive user artifacts."""
    return f"pipedrive_user_{user_id}"


def get_pipedrive_product_entity_id(*, product_id: int) -> str:
    """Generate entity ID for Pipedrive product artifacts."""
    return f"pipedrive_product_{product_id}"


def get_posthog_dashboard_entity_id(*, project_id: int, dashboard_id: int) -> str:
    """Generate entity ID for PostHog dashboard artifacts."""
    return f"posthog_dashboard_{project_id}_{dashboard_id}"


def get_posthog_insight_entity_id(*, project_id: int, insight_id: int) -> str:
    """Generate entity ID for PostHog insight artifacts."""
    return f"posthog_insight_{project_id}_{insight_id}"


def get_posthog_feature_flag_entity_id(*, project_id: int, flag_id: int) -> str:
    """Generate entity ID for PostHog feature flag artifacts."""
    return f"posthog_feature_flag_{project_id}_{flag_id}"


def get_posthog_annotation_entity_id(*, project_id: int, annotation_id: int) -> str:
    """Generate entity ID for PostHog annotation artifacts."""
    return f"posthog_annotation_{project_id}_{annotation_id}"


def get_posthog_experiment_entity_id(*, project_id: int, experiment_id: int) -> str:
    """Generate entity ID for PostHog experiment artifacts."""
    return f"posthog_experiment_{project_id}_{experiment_id}"


def get_posthog_survey_entity_id(*, project_id: int, survey_id: str) -> str:
    """Generate entity ID for PostHog survey artifacts."""
    return f"posthog_survey_{project_id}_{survey_id}"


def get_canva_design_entity_id(*, design_id: str) -> str:
    """Generate entity ID for Canva design artifacts."""
    return f"canva_design_{design_id}"


def get_teamwork_task_entity_id(*, task_id: int) -> str:
    """Generate entity ID for Teamwork task artifacts."""
    return f"teamwork_task_{task_id}"


def get_teamwork_project_entity_id(*, project_id: int) -> str:
    """Generate entity ID for Teamwork project artifacts."""
    return f"teamwork_project_{project_id}"


def get_teamwork_user_entity_id(*, user_id: int) -> str:
    """Generate entity ID for Teamwork user artifacts."""
    return f"teamwork_user_{user_id}"
