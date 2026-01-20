"""
Data models for warehouse query logging and execution.

This module provides Pydantic models for logging queries across all data warehouse
integrations (Snowflake, BigQuery, Redshift, etc.).
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Default SQL execution timeout in seconds (2 minutes)
DEFAULT_SQL_TIMEOUT_SECONDS = 120


class WarehouseSource(str, Enum):
    """Supported data warehouse sources."""

    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DATABRICKS = "databricks"
    POSTHOG = "posthog"


class QueryType(str, Enum):
    """Type of query being executed."""

    NATURAL_LANGUAGE = "natural_language"
    SQL = "sql"


class WarehouseQueryLog(BaseModel):
    """Model for logging warehouse queries to the database."""

    id: str = Field(..., description="Unique query identifier (UUID)")
    user_id: str | None = Field(
        None, description="User who executed the query (NULL for system queries)"
    )
    source: WarehouseSource = Field(..., description="Data warehouse source")
    query_type: QueryType = Field(..., description="Type of query")
    question: str = Field(..., description="Original NL question or SQL statement")
    generated_sql: str | None = Field(
        None, description="SQL generated from NL (NULL for direct SQL queries)"
    )
    semantic_model_id: str | None = Field(
        None, description="Reference to semantic model used (NULL if not applicable)"
    )
    execution_time_ms: int | None = Field(None, description="Query execution time in milliseconds")
    row_count: int | None = Field(None, description="Number of rows returned")
    success: bool = Field(..., description="Whether query succeeded")
    error_message: str | None = Field(None, description="Error details if query failed")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When query was executed"
    )


class QueryResult(BaseModel):
    """Result from executing a warehouse query."""

    success: bool
    data: list[dict] | None = None
    generated_sql: str | None = None
    execution_time_ms: int | None = None
    row_count: int | None = None
    error_message: str | None = None
    explanation: str | None = None


class SemanticModel(BaseModel):
    """Semantic model available for natural language queries."""

    id: str = Field(..., description="Unique identifier for the semantic model")
    name: str = Field(..., description="Display name of the semantic model")
    description: str | None = Field(
        None, description="Description of what data this model contains"
    )
    source: WarehouseSource = Field(..., description="Data warehouse source this model belongs to")


class CortexAnalystRequest(BaseModel):
    """Request to Snowflake Cortex Analyst API.

    Use one of:
    - semantic_model_file: For stage files (@stage/model.yaml)
    - semantic_model: For inline YAML string
    - semantic_view: For database objects (DB.SCHEMA.VIEW_NAME)
    """

    messages: list[dict[str, Any]]  # Array of message objects with role and content
    semantic_model_file: str | None = None  # For stage files: @stage/model.yaml
    semantic_model: str | None = None  # For inline YAML string
    semantic_view: str | None = None  # For database objects: DB.SCHEMA.VIEW_NAME
    warehouse: str | None = None


class CortexAnalystResponse(BaseModel):
    """Response from Snowflake Cortex Analyst API."""

    message: dict[str, Any]
    request_id: str
