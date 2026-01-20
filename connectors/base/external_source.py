from typing import Literal

from connectors.base.document_source import DocumentSource

# All external sources that can be ingested.
# Similar to DocumentSource, and arguably could be consolidated, but separate for now b/c e.g. GITHUB_PRS and GITHUB_CODE are different.
# This should be kept in sync with the TS ExternalSourceSchema!
ExternalSource = Literal[
    "slack",
    "github",
    "linear",
    "notion",
    "hubspot",
    "google_drive",
    "google_email",
    "jira",
    "confluence",
    "salesforce",
    "custom",
    "custom_data",
    "gong",
    "gather",
    "trello",
    "zendesk",
    "asana",
    "attio",
    "intercom",
    "fireflies",
    "gitlab",
    "pylon",
    "monday",
    "pipedrive",
    "clickup",
    "figma",
    "posthog",
    "canva",
    "teamwork",
]

DOC_SOURCE_TO_EXTERNAL_SOURCE: dict[DocumentSource, ExternalSource] = {
    DocumentSource.SLACK: "slack",
    DocumentSource.GITHUB_PRS: "github",
    DocumentSource.GITHUB_CODE: "github",
    DocumentSource.LINEAR: "linear",
    DocumentSource.NOTION: "notion",
    DocumentSource.HUBSPOT_DEAL: "hubspot",
    DocumentSource.GOOGLE_DRIVE: "google_drive",
    DocumentSource.GOOGLE_EMAIL: "google_email",
    DocumentSource.SALESFORCE: "salesforce",
    DocumentSource.JIRA: "jira",
    DocumentSource.CONFLUENCE: "confluence",
    DocumentSource.CUSTOM: "custom",
    DocumentSource.GONG: "gong",
    DocumentSource.GATHER: "gather",
    DocumentSource.TRELLO: "trello",
    DocumentSource.ZENDESK_TICKET: "zendesk",
    DocumentSource.ZENDESK_ARTICLE: "zendesk",
    DocumentSource.ASANA_TASK: "asana",
    DocumentSource.ATTIO_COMPANY: "attio",
    DocumentSource.ATTIO_PERSON: "attio",
    DocumentSource.ATTIO_DEAL: "attio",
    DocumentSource.INTERCOM: "intercom",
    DocumentSource.FIREFLIES_TRANSCRIPT: "fireflies",
    DocumentSource.GITLAB_MR: "gitlab",
    DocumentSource.GITLAB_CODE: "gitlab",
    DocumentSource.CUSTOM_DATA: "custom_data",
    DocumentSource.PYLON_ISSUE: "pylon",
    DocumentSource.MONDAY_ITEM: "monday",
    DocumentSource.PIPEDRIVE_DEAL: "pipedrive",
    DocumentSource.PIPEDRIVE_PERSON: "pipedrive",
    DocumentSource.PIPEDRIVE_ORGANIZATION: "pipedrive",
    DocumentSource.PIPEDRIVE_PRODUCT: "pipedrive",
    DocumentSource.CLICKUP_TASK: "clickup",
    DocumentSource.FIGMA_FILE: "figma",
    DocumentSource.FIGMA_COMMENT: "figma",
    DocumentSource.POSTHOG_DASHBOARD: "posthog",
    DocumentSource.POSTHOG_INSIGHT: "posthog",
    DocumentSource.POSTHOG_FEATURE_FLAG: "posthog",
    DocumentSource.POSTHOG_ANNOTATION: "posthog",
    DocumentSource.POSTHOG_EXPERIMENT: "posthog",
    DocumentSource.POSTHOG_SURVEY: "posthog",
    DocumentSource.CANVA_DESIGN: "canva",
    DocumentSource.TEAMWORK_TASK: "teamwork",
}


def get_external_source_for_document_source(document_source: DocumentSource) -> ExternalSource:
    """Map DocumentSource to ExternalSource for backfill notifications."""
    external_source = DOC_SOURCE_TO_EXTERNAL_SOURCE.get(document_source)
    if not external_source:
        raise ValueError(f"No ExternalSource found for DocumentSource: {document_source}")
    return external_source
