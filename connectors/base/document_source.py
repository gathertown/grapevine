"""
Document source enumeration for consistent source identification across the codebase.
"""

from dataclasses import dataclass
from enum import Enum


class DocumentSource(str, Enum):
    """Valid document sources for filtering and identification."""

    SLACK = "slack"
    GITHUB_PRS = "github"
    GITHUB_CODE = "github_code"
    LINEAR = "linear"
    NOTION = "notion"
    HUBSPOT_DEAL = "hubspot_deal"
    HUBSPOT_TICKET = "hubspot_ticket"
    HUBSPOT_COMPANY = "hubspot_company"
    HUBSPOT_CONTACT = "hubspot_contact"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_EMAIL = "google_email"
    SALESFORCE = "salesforce"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    CUSTOM = "custom"
    GONG = "gong"
    GATHER = "gather"
    TRELLO = "trello"
    ZENDESK_TICKET = "zendesk_ticket"
    ZENDESK_ARTICLE = "zendesk_article"
    ASANA_TASK = "asana_task"
    INTERCOM = "intercom"
    ATTIO_COMPANY = "attio_company"
    ATTIO_PERSON = "attio_person"
    ATTIO_DEAL = "attio_deal"
    FIREFLIES_TRANSCRIPT = "fireflies_transcript"
    GITLAB_MR = "gitlab_mr"
    GITLAB_CODE = "gitlab_code"
    CUSTOM_DATA = "custom_data"
    PYLON_ISSUE = "pylon_issue"
    CLICKUP_TASK = "clickup_task"
    MONDAY_ITEM = "monday_item"
    PIPEDRIVE_DEAL = "pipedrive_deal"
    PIPEDRIVE_PERSON = "pipedrive_person"
    PIPEDRIVE_ORGANIZATION = "pipedrive_organization"
    PIPEDRIVE_PRODUCT = "pipedrive_product"
    FIGMA_FILE = "figma_file"
    FIGMA_COMMENT = "figma_comment"
    POSTHOG_DASHBOARD = "posthog_dashboard"
    POSTHOG_INSIGHT = "posthog_insight"
    POSTHOG_FEATURE_FLAG = "posthog_feature_flag"
    POSTHOG_ANNOTATION = "posthog_annotation"
    POSTHOG_EXPERIMENT = "posthog_experiment"
    POSTHOG_SURVEY = "posthog_survey"
    CANVA_DESIGN = "canva_design"
    TEAMWORK_TASK = "teamwork_task"


@dataclass
class DocumentWithSourceAndMetadata[MetadataT]:
    id: str
    source: DocumentSource
    metadata: MetadataT


ALL_SOURCES = ", ".join([source.value for source in DocumentSource])
