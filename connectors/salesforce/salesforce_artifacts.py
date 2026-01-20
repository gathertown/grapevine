from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact

# Supported Salesforce object types
SUPPORTED_SALESFORCE_OBJECTS = Literal["Account", "Contact", "Opportunity", "Lead", "Case"]

# Concrete list of supported Salesforce object types
SALESFORCE_OBJECT_TYPES: list[SUPPORTED_SALESFORCE_OBJECTS] = [
    "Account",
    "Contact",
    "Opportunity",
    "Lead",
    "Case",
]


class SalesforceObjectArtifactMetadata(BaseModel):
    object_type: SUPPORTED_SALESFORCE_OBJECTS
    record_id: str
    record_name: str | None = None


class SalesforceObjectArtifactContent(BaseModel):
    record_data: dict[str, Any]

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class SalesforceObjectArtifact(BaseIngestArtifact):
    """Base class for all Salesforce object artifacts."""

    content: SalesforceObjectArtifactContent
    metadata: SalesforceObjectArtifactMetadata


class SalesforceAccountArtifact(SalesforceObjectArtifact):
    entity: ArtifactEntity = ArtifactEntity.SALESFORCE_ACCOUNT


class SalesforceContactArtifact(SalesforceObjectArtifact):
    entity: ArtifactEntity = ArtifactEntity.SALESFORCE_CONTACT


class SalesforceOpportunityArtifact(SalesforceObjectArtifact):
    entity: ArtifactEntity = ArtifactEntity.SALESFORCE_OPPORTUNITY


class SalesforceLeadArtifact(SalesforceObjectArtifact):
    entity: ArtifactEntity = ArtifactEntity.SALESFORCE_LEAD


class SalesforceCaseArtifact(SalesforceObjectArtifact):
    entity: ArtifactEntity = ArtifactEntity.SALESFORCE_CASE


SalesforceObjectArtifactType = (
    SalesforceAccountArtifact
    | SalesforceContactArtifact
    | SalesforceOpportunityArtifact
    | SalesforceLeadArtifact
    | SalesforceCaseArtifact
)
SalesforceObjectArtifactClassType = (
    type[SalesforceAccountArtifact]
    | type[SalesforceContactArtifact]
    | type[SalesforceOpportunityArtifact]
    | type[SalesforceLeadArtifact]
    | type[SalesforceCaseArtifact]
)

# Type mapping from object type strings to artifact classes
SALESFORCE_ARTIFACT_MAPPING: dict[
    SUPPORTED_SALESFORCE_OBJECTS, SalesforceObjectArtifactClassType
] = {
    "Account": SalesforceAccountArtifact,
    "Contact": SalesforceContactArtifact,
    "Opportunity": SalesforceOpportunityArtifact,
    "Lead": SalesforceLeadArtifact,
    "Case": SalesforceCaseArtifact,
}

# Type mapping from object type strings to entity types
SALESFORCE_ENTITY_MAPPING: dict[SUPPORTED_SALESFORCE_OBJECTS, ArtifactEntity] = {
    "Account": ArtifactEntity.SALESFORCE_ACCOUNT,
    "Contact": ArtifactEntity.SALESFORCE_CONTACT,
    "Opportunity": ArtifactEntity.SALESFORCE_OPPORTUNITY,
    "Lead": ArtifactEntity.SALESFORCE_LEAD,
    "Case": ArtifactEntity.SALESFORCE_CASE,
}


def get_salesforce_artifact_class(
    object_type: SUPPORTED_SALESFORCE_OBJECTS,
) -> type[SalesforceObjectArtifact]:
    """Get the appropriate artifact class for a Salesforce object type."""
    if object_type not in SALESFORCE_ARTIFACT_MAPPING:
        raise ValueError(f"Unknown Salesforce object type: {object_type}")
    return SALESFORCE_ARTIFACT_MAPPING[object_type]


def get_salesforce_entity_type(object_type: SUPPORTED_SALESFORCE_OBJECTS) -> ArtifactEntity:
    """Get the appropriate entity type for a Salesforce object type."""
    if object_type not in SALESFORCE_ENTITY_MAPPING:
        raise ValueError(f"Unknown Salesforce object type: {object_type}")
    return SALESFORCE_ENTITY_MAPPING[object_type]
