"""Figma API client module."""

from connectors.figma.client.figma_client import (
    FigmaAPIError,
    FigmaClient,
    FigmaComment,
    FigmaFile,
    FigmaFileMetadata,
    FigmaProject,
    FigmaRateLimitInfo,
    FigmaUser,
    FigmaVersion,
    get_figma_client_for_tenant,
)

__all__ = [
    "FigmaAPIError",
    "FigmaClient",
    "FigmaComment",
    "FigmaFile",
    "FigmaFileMetadata",
    "FigmaProject",
    "FigmaRateLimitInfo",
    "FigmaUser",
    "FigmaVersion",
    "get_figma_client_for_tenant",
]
