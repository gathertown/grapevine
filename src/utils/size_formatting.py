"""Utility functions for formatting file and data sizes."""


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 KB", "2.3 MB")
    """
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
