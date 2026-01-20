import json
from typing import Any

from pydantic import BaseModel, Field, model_validator
from turbopuffer.types import Filter

from connectors.base.document_source import ALL_SOURCES, DocumentSource
from src.permissions.models import PermissionAudience
from src.permissions.utils import should_include_private_documents
from src.utils.date_utils import validate_and_convert_date


class SearchFilters(BaseModel):
    """Search filters used to narrow down results from search tools."""

    @model_validator(mode="before")
    @classmethod
    def parse_string_input(cls, data: Any) -> Any:
        """Parse filters from JSON string if provided as string."""
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON string for filters: {e}")
        return data

    sources: list[DocumentSource] = Field(
        default=[],
        description=f"Source(s) to filter by: {ALL_SOURCES}. Pass an empty list to include all sources. Pass multiple sources to include results from any of the provided sources. Pass only a single source if you are using provenance!",
    )
    date_from: str | None = Field(
        default=None,
        description="Start date in YYYY-MM-DD format. Include this to filter for only results created on or after this date. Can be useful in situations like checking for results newer than one with a known date. Pass null or an empty string to skip this filter.",
    )
    date_to: str | None = Field(
        default=None,
        description="End date in YYYY-MM-DD format. Include this to filter for only results created on or before this date. Can be useful in situations like checking for results older than one with a known date. Pass null or an empty string to skip this filter.",
    )
    provenance: str | None = Field(
        default=None,
        description=f"""Source-specific provenance filter. Important: Only supported when called with a single source value in `sources`!
- For {DocumentSource.SLACK.value}: channel name or ID, e.g. "team-platform" or "C0123456789"
- For {DocumentSource.GITHUB_PRS.value} or {DocumentSource.GITHUB_CODE.value}: repository name, e.g. "your-repo-name-here"
- For {DocumentSource.LINEAR.value}: team name, e.g. "Engineering"
- For {DocumentSource.CUSTOM.value}: collection name, e.g. "customer-feedback"
- For all other sources: DO NOT USE, not supported
Specify exactly one source if you are using provenance!

Pass null or an empty string to skip this filter.
""",
    )
    document_id: str | None = Field(
        default=None,
        description="Exact document ID to filter by. If provided, all other filters are ignored. Pass null or an empty string to skip this filter.",
    )


def build_opensearch_filters(
    filters: SearchFilters,
    permission_principal_token: str | None,
    permission_audience: PermissionAudience | None = None,
) -> dict[str, Any] | None:
    """Build OpenSearch filters from SearchFilters object.

    Args:
        filters: Search filters to apply
        permission_principal_token: User's permission token for access control
        permission_audience: Audience policy ('public' or 'private') for filtering documents
    """
    # If document_id is provided, use only that filter (primary key lookup)
    if filters.document_id:
        return {"term": {"id": filters.document_id}}

    opensearch_filters: list[dict[str, Any]] = []

    if filters.sources and len(filters.sources) > 0:
        if len(filters.sources) == 1:
            opensearch_filters.append({"term": {"source": filters.sources[0].value}})
        else:
            opensearch_filters.append(
                {"terms": {"source": [source.value for source in filters.sources]}}
            )

    if filters.date_from or filters.date_to:
        date_range = {}
        if filters.date_from:
            date_range["gte"] = filters.date_from
        if filters.date_to:
            date_range["lte"] = filters.date_to
        opensearch_filters.append({"range": {"source_created_at": date_range}})

    # Handle provenance filtering based on source type
    if filters.provenance and filters.sources and len(filters.sources) > 0:
        # If multiple sources are provided, provenance filtering only applies if all sources
        # use the same provenance field structure
        if len(filters.sources) == 1:
            source = filters.sources[0]
            # NOTE: The .keyword suffixes are required because our `metadata` field is a flattened object in OpenSearch
            if source == DocumentSource.SLACK:
                # Try both channel_id and channel_name
                opensearch_filters.append(
                    {
                        "bool": {
                            "should": [
                                {"term": {"metadata.channel_id.keyword": filters.provenance}},
                                {"term": {"metadata.channel_name.keyword": filters.provenance}},
                            ]
                        }
                    }
                )
            elif source in [DocumentSource.GITHUB_PRS, DocumentSource.GITHUB_CODE]:
                opensearch_filters.append(
                    {"term": {"metadata.repository.keyword": filters.provenance}}
                )
            elif source == DocumentSource.LINEAR:
                opensearch_filters.append(
                    {"term": {"metadata.team_name.keyword": filters.provenance}}
                )
            elif source == DocumentSource.CUSTOM:
                opensearch_filters.append(
                    {"term": {"metadata.collection_name.keyword": filters.provenance}}
                )
            else:
                raise ValueError(f"Provenance filtering is not supported for source: {source}")
        else:
            raise ValueError(
                "Provenance filtering is only supported for a single source. Please provide a single source if you are using provenance!"
            )

    permission_filter: dict[str, Any]
    if should_include_private_documents(permission_audience, permission_principal_token):
        permission_filter = {
            "bool": {
                "should": [
                    {"term": {"permission_policy": "tenant"}},
                    {
                        "bool": {
                            "must": [
                                {"term": {"permission_policy": "private"}},
                                {"term": {"permission_allowed_tokens": permission_principal_token}},
                            ]
                        }
                    },
                ]
            }
        }
    else:
        permission_filter = {"term": {"permission_policy": "tenant"}}

    opensearch_filters.append(permission_filter)

    # Combine all filters
    if not opensearch_filters:
        return None
    elif len(opensearch_filters) == 1:
        return opensearch_filters[0]
    else:
        return {"bool": {"must": opensearch_filters}}


def build_postgres_filters(
    filters: SearchFilters,
    permission_principal_token: str | None,
    permission_audience: PermissionAudience | None = None,
) -> tuple[str, list[Any]]:
    """Build PostgreSQL filter conditions and parameters from SearchFilters object.

    Args:
        filters: Search filters to apply
        permission_principal_token: User's permission token for access control
        permission_audience: Audience policy ('public' or 'private') for filtering documents

    Returns:
        tuple: (where_clause, params) where where_clause is SQL and params is list of values
    """
    # If document_id is provided, use only that filter (primary key lookup)
    if filters.document_id:
        return "c.document_id = $1", [filters.document_id]

    conditions = []
    params = []
    param_count = 0

    if filters.sources and len(filters.sources) > 0:
        if len(filters.sources) == 1:
            param_count += 1
            conditions.append(f"d.source = ${param_count}")
            params.append(filters.sources[0].value)
        else:
            param_count += 1
            conditions.append(f"d.source = ANY(${param_count}::varchar[])")
            params.append([source.value for source in filters.sources])  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    if filters.date_from:
        param_count += 1
        conditions.append(f"d.source_created_at::date >= ${param_count}")
        params.append(validate_and_convert_date(filters.date_from))  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    if filters.date_to:
        param_count += 1
        conditions.append(f"d.source_created_at::date <= ${param_count}")
        params.append(validate_and_convert_date(filters.date_to))  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    # Handle provenance filtering based on source type
    if filters.provenance and filters.sources and len(filters.sources) > 0:
        if len(filters.sources) == 1:
            source = filters.sources[0]
            # NOTE: We use 'd.metadata @> jsonb_build_object(key, value)' instead of 'd.metadata->>key = value'
            # because the @> containment operator can leverage GIN indexes on the metadata JSONB field,
            # providing *much* better query performance than text extraction with ->>
            if source == DocumentSource.SLACK:
                param_count += 1
                conditions.append(
                    f"(d.metadata @> jsonb_build_object('channel_id', ${param_count}::text) OR d.metadata @> jsonb_build_object('channel_name', ${param_count}::text))"
                )
                params.append(filters.provenance)
            elif source in [DocumentSource.GITHUB_PRS, DocumentSource.GITHUB_CODE]:
                param_count += 1
                conditions.append(
                    f"d.metadata @> jsonb_build_object('repository', ${param_count}::text)"
                )
                params.append(filters.provenance)
            elif source == DocumentSource.LINEAR:
                param_count += 1
                conditions.append(
                    f"d.metadata @> jsonb_build_object('team_name', ${param_count}::text)"
                )
                params.append(filters.provenance)
            elif source == DocumentSource.CUSTOM:
                param_count += 1
                conditions.append(
                    f"d.metadata @> jsonb_build_object('collection_name', ${param_count}::text)"
                )
                params.append(filters.provenance)
            else:
                raise ValueError(f"Provenance filtering is not supported for source: {source}")
        else:
            raise ValueError(
                "Provenance filtering is only supported for a single source. Please provide a single source if you are using provenance!"
            )

    if should_include_private_documents(permission_audience, permission_principal_token):
        assert permission_principal_token is not None
        param_count += 1
        permission_condition = f"""
        (dp.permission_policy = 'tenant' OR
         (dp.permission_policy = 'private' AND ${param_count}::text = ANY(dp.permission_allowed_tokens)))
        """
        conditions.append(permission_condition.strip())
        params.append(permission_principal_token)
    else:
        conditions.append("dp.permission_policy = 'tenant'")

    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params


def build_turbopuffer_filters(
    filters: SearchFilters,
    permission_principal_token: str | None,
    permission_audience: PermissionAudience | None = None,
) -> Filter | None:
    """Build Turbopuffer filter conditions from SearchFilters object.

    Args:
        filters: Search filters to apply
        permission_principal_token: User's permission token for access control
        permission_audience: Audience policy ('public' or 'private') for filtering documents

    Returns:
        Filter object in Turbopuffer's native tuple format, or None if no filters
    """
    # If document_id is provided, use only that filter (primary key lookup)
    if filters.document_id:
        return ("document_id", "Eq", filters.document_id)

    conditions: list[Filter] = []

    # Source filtering
    if filters.sources and len(filters.sources) > 0:
        if len(filters.sources) == 1:
            conditions.append(("source", "Eq", filters.sources[0].value))
        else:
            # Multiple sources - create OR condition
            source_conditions: list[Filter] = [
                ("source", "Eq", source.value) for source in filters.sources
            ]
            conditions.append(("Or", source_conditions))

    # Date range filtering
    if filters.date_from:
        validated_date = validate_and_convert_date(filters.date_from)
        if validated_date:
            conditions.append(("source_created_at", "Gte", validated_date.isoformat()))

    if filters.date_to:
        validated_date = validate_and_convert_date(filters.date_to)
        if validated_date:
            conditions.append(("source_created_at", "Lte", validated_date.isoformat()))

    # Provenance filtering based on source type
    if filters.provenance and filters.sources and len(filters.sources) > 0:
        if len(filters.sources) == 1:
            source = filters.sources[0]
            if source == DocumentSource.SLACK:
                # For Slack, we need to check both channel_id and channel_name
                slack_conditions: list[Filter] = [
                    ("slack_channel_id", "Eq", filters.provenance),
                    ("slack_channel_name", "Eq", filters.provenance),
                ]
                conditions.append(("Or", slack_conditions))
            elif source in [DocumentSource.GITHUB_PRS, DocumentSource.GITHUB_CODE]:
                conditions.append(("github_repository", "Eq", filters.provenance))
            elif source == DocumentSource.LINEAR:
                conditions.append(("linear_team_name", "Eq", filters.provenance))
            elif source == DocumentSource.CUSTOM:
                conditions.append(("metadata.collection_name", "Eq", filters.provenance))
            else:
                raise ValueError(f"Provenance filtering is not supported for source: {source}")
        else:
            raise ValueError(
                "Provenance filtering is only supported for a single source. Please provide a single source if you are using provenance!"
            )

    if should_include_private_documents(permission_audience, permission_principal_token):
        private_access_conditions: list[Filter] = [
            ("permission_policy", "Eq", "private"),
            ("permission_allowed_tokens", "Contains", permission_principal_token),
        ]
        permission_filters: list[Filter] = [
            ("permission_policy", "Eq", "tenant"),
            ("And", private_access_conditions),
        ]
        permission_condition: Filter = ("Or", permission_filters)
        conditions.append(permission_condition)
    else:
        conditions.append(("permission_policy", "Eq", "tenant"))

    # Return appropriate filter structure
    if not conditions:
        return None
    elif len(conditions) == 1:
        return conditions[0]
    else:
        return ("And", conditions)


def get_filter_description() -> str:
    """Get standardized filter description for tool documentation."""
    return f"""Filtering options:
- sources: Filter by document source(s) ({ALL_SOURCES}). If no sources are provided, all sources will be included.
- date_from/date_to: Filter by date range in YYYY-MM-DD format
- provenance: Filter by source-specific context:
  • {DocumentSource.SLACK.value}: channel name or channel ID
  • {DocumentSource.GITHUB_PRS.value} or {DocumentSource.GITHUB_CODE.value}: repository name
  • {DocumentSource.LINEAR.value}: team name
  • {DocumentSource.CUSTOM.value}: collection name
  • other sources: DO NOT USE, not supported
  Specify exactly one source if you are using provenance!
- document_id: Filter to a specific document by exact ID (when provided, all other filters are ignored)"""
