"""Permissions module for document access control."""

from .models import DocumentPermissions
from .service import PermissionsService

__all__ = [
    "DocumentPermissions",
    "PermissionsService",
]
