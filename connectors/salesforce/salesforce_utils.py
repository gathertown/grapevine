"""Utility functions for Salesforce record processing."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from connectors.base import get_salesforce_object_entity_id
from connectors.salesforce.salesforce_artifacts import (
    SALESFORCE_ARTIFACT_MAPPING,
    SUPPORTED_SALESFORCE_OBJECTS,
    SalesforceObjectArtifactClassType,
    SalesforceObjectArtifactContent,
    SalesforceObjectArtifactMetadata,
    SalesforceObjectArtifactType,
)

logger = logging.getLogger(__name__)


def create_salesforce_artifact(
    job_id: str,
    object_type: SUPPORTED_SALESFORCE_OBJECTS,
    record_data: dict[str, object],
) -> SalesforceObjectArtifactType | None:
    """Create a Salesforce artifact from record data."""
    try:
        record_id = record_data.get("Id")
        if not isinstance(record_id, str):
            logger.warning(f"Invalid Id field found in {object_type} record data: {record_id}")
            return None

        entity_id = get_salesforce_object_entity_id(record_id=record_id)

        # Extract record name - different objects have different name fields
        record_name = None
        name_fields = ["Name", "Subject", "Title", "FirstName", "LastName"]
        for field in name_fields:
            if field in record_data and record_data[field]:
                if field in ["FirstName", "LastName"]:
                    # For contacts, combine first and last name
                    first_name = record_data.get("FirstName", "")
                    last_name = record_data.get("LastName", "")
                    record_name = f"{first_name} {last_name}".strip()
                    break
                else:
                    record_name = str(record_data[field])
                    break

        # Get the appropriate artifact class for this object type
        if object_type not in SALESFORCE_ARTIFACT_MAPPING:
            logger.error(f"Unknown Salesforce object type: {object_type}")
            return None

        artifact_class: SalesforceObjectArtifactClassType = SALESFORCE_ARTIFACT_MAPPING[object_type]

        artifact = artifact_class(
            entity_id=entity_id,
            ingest_job_id=UUID(job_id),
            content=SalesforceObjectArtifactContent(record_data=record_data),
            metadata=SalesforceObjectArtifactMetadata(
                object_type=object_type,
                record_id=record_id,
                record_name=record_name,
            ),
            source_updated_at=datetime.now(tz=UTC),
        )

        return artifact

    except Exception as e:
        logger.error(
            f"Error creating {object_type} artifact for record {record_data.get('Id', 'unknown')}: {e}"
        )
        return None
