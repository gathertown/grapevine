"""Pipedrive artifact to document transformers.

Transforms Pipedrive artifacts into searchable documents.
Includes hydration for enriching documents with user/org/person names.
"""

import json
from typing import Any

import asyncpg

from connectors.base.base_transformer import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveDealArtifact,
    PipedriveOrganizationArtifact,
    PipedrivePersonArtifact,
    PipedriveProductArtifact,
    PipedriveUserArtifact,
)
from connectors.pipedrive.pipedrive_deal_document import PipedriveDealDocument
from connectors.pipedrive.pipedrive_models import PIPEDRIVE_PERSON_LABELS_KEY
from connectors.pipedrive.pipedrive_organization_document import PipedriveOrganizationDocument
from connectors.pipedrive.pipedrive_person_document import PipedrivePersonDocument
from connectors.pipedrive.pipedrive_product_document import PipedriveProductDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool

logger = get_logger(__name__)


class PipedriveHydrator:
    """Hydrates Pipedrive documents with reference data from stored artifacts.

    Pipedrive API returns IDs for users, persons, and organizations.
    This hydrator fetches cached reference artifacts to enrich documents
    with human-readable names.
    """

    def __init__(
        self,
        users: dict[int, PipedriveUserArtifact] | None = None,
        persons: dict[int, PipedrivePersonArtifact] | None = None,
        organizations: dict[int, PipedriveOrganizationArtifact] | None = None,
        person_labels: dict[int, str] | None = None,
    ):
        """Initialize the hydrator with reference data.

        Args:
            users: Map of user_id -> user artifact
            persons: Map of person_id -> person artifact
            organizations: Map of org_id -> organization artifact
            person_labels: Map of label_id -> label name
        """
        self.users = users or {}
        self.persons = persons or {}
        self.organizations = organizations or {}
        self.person_labels = person_labels or {}

    def get_user_name(self, user_id: int | None) -> str | None:
        """Get user name from reference data."""
        if not user_id:
            return None
        user = self.users.get(user_id)
        if user:
            return user.metadata.name
        return None

    def get_user_email(self, user_id: int | None) -> str | None:
        """Get user email from reference data."""
        if not user_id:
            return None
        user = self.users.get(user_id)
        if user:
            return user.metadata.email
        return None

    def get_person_name(self, person_id: int | None) -> str | None:
        """Get person name from reference data."""
        if not person_id:
            return None
        person = self.persons.get(person_id)
        if person:
            return person.metadata.name
        return None

    def get_person_email(self, person_id: int | None) -> str | None:
        """Get person email from reference data."""
        if not person_id:
            return None
        person = self.persons.get(person_id)
        if person:
            return person.metadata.email
        return None

    def get_org_name(self, org_id: int | None) -> str | None:
        """Get organization name from reference data."""
        if not org_id:
            return None
        org = self.organizations.get(org_id)
        if org:
            return org.metadata.name
        return None

    def get_label_names(self, label_ids: list[int] | None) -> list[str]:
        """Get label names from label IDs.

        Args:
            label_ids: List of label IDs to resolve

        Returns:
            List of label names (unknown IDs are skipped)
        """
        if not label_ids:
            return []
        names = []
        for label_id in label_ids:
            name = self.person_labels.get(label_id)
            if name:
                names.append(name)
        return names

    @classmethod
    async def from_database(
        cls,
        db_client: Any,
        tenant_id: str,
    ) -> "PipedriveHydrator":
        """Load reference data from database.

        Args:
            db_client: Database client for tenant
            tenant_id: Tenant ID

        Returns:
            PipedriveHydrator instance with loaded reference data
        """
        from src.ingest.repositories.artifact_repository import ArtifactRepository

        repo = ArtifactRepository(db_client)

        users: dict[int, PipedriveUserArtifact] = {}
        persons: dict[int, PipedrivePersonArtifact] = {}
        organizations: dict[int, PipedriveOrganizationArtifact] = {}

        # Load users - get_artifacts returns typed artifacts directly
        user_artifacts = await repo.get_artifacts(PipedriveUserArtifact)
        for user in user_artifacts:
            users[user.metadata.user_id] = user

        # Load persons
        person_artifacts = await repo.get_artifacts(PipedrivePersonArtifact)
        for person in person_artifacts:
            persons[person.metadata.person_id] = person

        # Load organizations
        org_artifacts = await repo.get_artifacts(PipedriveOrganizationArtifact)
        for org in org_artifacts:
            organizations[org.metadata.org_id] = org

        # Load person labels from tenant config
        person_labels: dict[int, str] = {}
        labels_json = await get_config_value_with_pool(PIPEDRIVE_PERSON_LABELS_KEY, db_client)
        if labels_json and isinstance(labels_json, str):
            try:
                # Labels are stored as {"id": "name", ...} with string keys
                raw_labels = json.loads(labels_json)
                person_labels = {int(k): v for k, v in raw_labels.items()}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse person labels: {e}")

        logger.info(
            f"Loaded Pipedrive reference data: {len(users)} users, "
            f"{len(persons)} persons, {len(organizations)} organizations, "
            f"{len(person_labels)} person labels"
        )

        return cls(
            users=users,
            persons=persons,
            organizations=organizations,
            person_labels=person_labels,
        )


class PipedriveDealTransformer(BaseTransformer[PipedriveDealDocument]):
    """Transforms Pipedrive deal artifacts into documents."""

    def __init__(self):
        """Initialize the transformer."""
        super().__init__(DocumentSource.PIPEDRIVE_DEAL)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PipedriveDealDocument]:
        """Transform Pipedrive deal artifacts into documents.

        Args:
            entity_ids: List of deal entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PipedriveDealDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Load hydrator with reference data
        hydrator = await PipedriveHydrator.from_database(readonly_db_pool, "")

        # Get deal artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(PipedriveDealArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Pipedrive deal artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Pipedrive deal artifact {artifact.id}", counter
            ):
                deal_data = artifact.content.deal_data

                # Get enriched names from hydrator
                owner_id = artifact.metadata.owner_id
                person_id = artifact.metadata.person_id
                org_id = artifact.metadata.org_id

                # Build hydrated metadata dict
                hydrated_metadata: dict[str, Any] = {
                    "owner_name": hydrator.get_user_name(owner_id),
                    "owner_email": hydrator.get_user_email(owner_id),
                    "person_name": hydrator.get_person_name(person_id),
                    "person_email": hydrator.get_person_email(person_id),
                    "org_name": hydrator.get_org_name(org_id),
                    "stage_name": deal_data.get("stage", {}).get("name")
                    if isinstance(deal_data.get("stage"), dict)
                    else None,
                    "pipeline_name": deal_data.get("pipeline", {}).get("name")
                    if isinstance(deal_data.get("pipeline"), dict)
                    else None,
                }

                document = PipedriveDealDocument.from_artifact(
                    artifact=artifact,
                    hydrated_metadata=hydrated_metadata,
                )
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} deals")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Pipedrive deal transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PipedrivePersonTransformer(BaseTransformer[PipedrivePersonDocument]):
    """Transforms Pipedrive person artifacts into documents."""

    def __init__(self):
        """Initialize the transformer."""
        super().__init__(DocumentSource.PIPEDRIVE_PERSON)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PipedrivePersonDocument]:
        """Transform Pipedrive person artifacts into documents.

        Args:
            entity_ids: List of person entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PipedrivePersonDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Load hydrator with reference data
        hydrator = await PipedriveHydrator.from_database(readonly_db_pool, "")

        # Get person artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(PipedrivePersonArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Pipedrive person artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Pipedrive person artifact {artifact.id}", counter
            ):
                # Get enriched names from hydrator
                owner_id = artifact.metadata.owner_id
                org_id = artifact.metadata.org_id

                # Get label IDs from raw person data and resolve to names
                label_ids = artifact.content.person_data.get("label_ids") or []
                label_names = hydrator.get_label_names(label_ids)

                # Build hydrated metadata dict
                hydrated_metadata: dict[str, Any] = {
                    "org_name": hydrator.get_org_name(org_id),
                    "owner_name": hydrator.get_user_name(owner_id),
                    "owner_email": hydrator.get_user_email(owner_id),
                    "label_names": label_names if label_names else None,
                }

                document = PipedrivePersonDocument.from_artifact(
                    artifact=artifact,
                    hydrated_metadata=hydrated_metadata,
                )
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} persons")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Pipedrive person transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PipedriveOrganizationTransformer(BaseTransformer[PipedriveOrganizationDocument]):
    """Transforms Pipedrive organization artifacts into documents."""

    def __init__(self):
        """Initialize the transformer."""
        super().__init__(DocumentSource.PIPEDRIVE_ORGANIZATION)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PipedriveOrganizationDocument]:
        """Transform Pipedrive organization artifacts into documents.

        Args:
            entity_ids: List of organization entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PipedriveOrganizationDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Load hydrator with reference data
        hydrator = await PipedriveHydrator.from_database(readonly_db_pool, "")

        # Get organization artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(
            PipedriveOrganizationArtifact, entity_ids
        )

        logger.info(
            f"Loaded {len(artifacts)} Pipedrive organization artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform Pipedrive organization artifact {artifact.id}",
                counter,
            ):
                # Get owner name from hydrator
                owner_id = artifact.metadata.owner_id

                # Build hydrated metadata dict
                hydrated_metadata: dict[str, Any] = {
                    "owner_name": hydrator.get_user_name(owner_id),
                    "owner_email": hydrator.get_user_email(owner_id),
                }

                document = PipedriveOrganizationDocument.from_artifact(
                    artifact=artifact,
                    hydrated_metadata=hydrated_metadata,
                )
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} organizations")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Pipedrive organization transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PipedriveProductTransformer(BaseTransformer[PipedriveProductDocument]):
    """Transforms Pipedrive product artifacts into documents."""

    def __init__(self):
        """Initialize the transformer."""
        super().__init__(DocumentSource.PIPEDRIVE_PRODUCT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PipedriveProductDocument]:
        """Transform Pipedrive product artifacts into documents.

        Args:
            entity_ids: List of product entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PipedriveProductDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Load hydrator with reference data
        hydrator = await PipedriveHydrator.from_database(readonly_db_pool, "")

        # Get product artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(PipedriveProductArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Pipedrive product artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Pipedrive product artifact {artifact.id}", counter
            ):
                # Get owner name from hydrator
                owner_id = artifact.metadata.owner_id

                # Build hydrated metadata dict
                hydrated_metadata: dict[str, Any] = {
                    "owner_name": hydrator.get_user_name(owner_id),
                    "owner_email": hydrator.get_user_email(owner_id),
                }

                document = PipedriveProductDocument.from_artifact(
                    artifact=artifact,
                    hydrated_metadata=hydrated_metadata,
                )
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} products")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Pipedrive product transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
