"""Pipedrive CRM connector for Grapevine.

Pipedrive is a sales CRM platform. This connector syncs deals, persons,
organizations, activities, and notes.

API Documentation:
- API v1/v2: https://developers.pipedrive.com/docs/api/v1
- OAuth: https://pipedrive.readme.io/docs/marketplace-oauth-authorization
- Rate limits: Token-based daily budget + burst limits per 2-second window
"""

from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveActivityArtifact,
    PipedriveDealArtifact,
    PipedriveNoteArtifact,
    PipedriveOrganizationArtifact,
    PipedrivePersonArtifact,
    PipedriveProductArtifact,
    PipedriveUserArtifact,
)
from connectors.pipedrive.pipedrive_citation_resolver import (
    PipedriveDealCitationResolver,
    PipedriveOrganizationCitationResolver,
    PipedrivePersonCitationResolver,
    PipedriveProductCitationResolver,
)
from connectors.pipedrive.pipedrive_deal_document import PipedriveDealDocument
from connectors.pipedrive.pipedrive_organization_document import (
    PipedriveOrganizationDocument,
)
from connectors.pipedrive.pipedrive_person_document import PipedrivePersonDocument
from connectors.pipedrive.pipedrive_product_document import PipedriveProductDocument
from connectors.pipedrive.pipedrive_pruner import PipedrivePruner, pipedrive_pruner

__all__ = [
    # Artifacts
    "PipedriveDealArtifact",
    "PipedrivePersonArtifact",
    "PipedriveOrganizationArtifact",
    "PipedriveProductArtifact",
    "PipedriveActivityArtifact",
    "PipedriveNoteArtifact",
    "PipedriveUserArtifact",
    # Documents
    "PipedriveDealDocument",
    "PipedrivePersonDocument",
    "PipedriveOrganizationDocument",
    "PipedriveProductDocument",
    # Citation Resolvers
    "PipedriveDealCitationResolver",
    "PipedrivePersonCitationResolver",
    "PipedriveOrganizationCitationResolver",
    "PipedriveProductCitationResolver",
    # Pruner
    "PipedrivePruner",
    "pipedrive_pruner",
]
