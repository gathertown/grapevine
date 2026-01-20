# Artifacts
# Transformers
# Extractors
# Documents
# Lazy imports to avoid circular dependencies with src.jobs.models
from typing import TYPE_CHECKING

from connectors.salesforce.salesforce_account_document import SalesforceAccountDocument
from connectors.salesforce.salesforce_artifacts import (
    SALESFORCE_ARTIFACT_MAPPING,
    SALESFORCE_ENTITY_MAPPING,
    SALESFORCE_OBJECT_TYPES,
    SUPPORTED_SALESFORCE_OBJECTS,
    SalesforceAccountArtifact,
    SalesforceCaseArtifact,
    SalesforceContactArtifact,
    SalesforceLeadArtifact,
    SalesforceObjectArtifact,
    SalesforceObjectArtifactClassType,
    SalesforceObjectArtifactContent,
    SalesforceObjectArtifactMetadata,
    SalesforceObjectArtifactType,
    SalesforceOpportunityArtifact,
    get_salesforce_artifact_class,
    get_salesforce_entity_type,
)
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceChunkMetadata,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)
from connectors.salesforce.salesforce_case_document import SalesforceCaseDocument

# Citation Resolvers
from connectors.salesforce.salesforce_citation_resolver import SalesforceCitationResolver
from connectors.salesforce.salesforce_contact_document import SalesforceContactDocument
from connectors.salesforce.salesforce_lead_document import SalesforceLeadDocument
from connectors.salesforce.salesforce_opportunity_document import SalesforceOpportunityDocument

# Pruners
from connectors.salesforce.salesforce_pruner import SalesforcePruner, salesforce_pruner
from connectors.salesforce.salesforce_transformer import SalesforceTransformer

if TYPE_CHECKING:
    from connectors.salesforce.salesforce_backfill_extractor import SalesforceBackfillExtractor
    from connectors.salesforce.salesforce_backfill_root_extractor import (
        SalesforceBackfillRootExtractor,
    )
    from connectors.salesforce.salesforce_cdc_extractor import SalesforceCDCExtractor
    from connectors.salesforce.salesforce_cdc_manager import SalesforceCDCManager
    from connectors.salesforce.salesforce_object_sync_extractor import SalesforceObjectSyncExtractor


def __getattr__(name: str):
    """Lazy load extractor and manager classes to avoid circular imports."""
    if name == "SalesforceBackfillExtractor":
        from connectors.salesforce.salesforce_backfill_extractor import SalesforceBackfillExtractor

        return SalesforceBackfillExtractor
    elif name == "SalesforceBackfillRootExtractor":
        from connectors.salesforce.salesforce_backfill_root_extractor import (
            SalesforceBackfillRootExtractor,
        )

        return SalesforceBackfillRootExtractor
    elif name == "SalesforceCDCExtractor":
        from connectors.salesforce.salesforce_cdc_extractor import SalesforceCDCExtractor

        return SalesforceCDCExtractor
    elif name == "SalesforceCDCManager":
        from connectors.salesforce.salesforce_cdc_manager import SalesforceCDCManager

        return SalesforceCDCManager
    elif name == "SalesforceObjectSyncExtractor":
        from connectors.salesforce.salesforce_object_sync_extractor import (
            SalesforceObjectSyncExtractor,
        )

        return SalesforceObjectSyncExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Artifacts
    "SalesforceObjectArtifact",
    "SalesforceObjectArtifactMetadata",
    "SalesforceObjectArtifactContent",
    "SalesforceAccountArtifact",
    "SalesforceContactArtifact",
    "SalesforceOpportunityArtifact",
    "SalesforceLeadArtifact",
    "SalesforceCaseArtifact",
    "SalesforceObjectArtifactType",
    "SalesforceObjectArtifactClassType",
    "SUPPORTED_SALESFORCE_OBJECTS",
    "SALESFORCE_OBJECT_TYPES",
    "SALESFORCE_ARTIFACT_MAPPING",
    "SALESFORCE_ENTITY_MAPPING",
    "get_salesforce_artifact_class",
    "get_salesforce_entity_type",
    # Citation Resolvers
    "SalesforceCitationResolver",
    # Documents
    "BaseSalesforceDocument",
    "BaseSalesforceDocumentMetadata",
    "BaseSalesforceChunk",
    "BaseSalesforceChunkMetadata",
    "SalesforceAccountDocument",
    "SalesforceCaseDocument",
    "SalesforceContactDocument",
    "SalesforceLeadDocument",
    "SalesforceOpportunityDocument",
    # Transformers
    "SalesforceTransformer",
    # Extractors
    "SalesforceBackfillExtractor",
    "SalesforceBackfillRootExtractor",
    "SalesforceCDCExtractor",
    "SalesforceObjectSyncExtractor",
    # Pruners
    "SalesforcePruner",
    "salesforce_pruner",
    # CDC Manager
    "SalesforceCDCManager",
]
