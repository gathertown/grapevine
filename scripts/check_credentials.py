#!/usr/bin/env python3
"""Check credentials validity for development environment."""

import os
import sys
from datetime import UTC, datetime


def print_aws_login_instructions():
    """Print instructions for fixing AWS credential issues."""
    print("")
    print("To fix this:")
    print("  1. Stop Tilt (Ctrl+C)")
    print("  2. Run: AWS_PROFILE=<your profile> aws sso login")
    print(
        "  2. Run: eval $(aws configure export-credentials --format env --profile <your profile>)"
    )
    print("  3. Restart Tilt from the same terminal")
    print("")
    print("Note: AWS credentials must be configured in the same terminal session where Tilt runs")


def parse_aws_expiration_date(date_str: str) -> datetime | None:
    """Parse AWS credential expiration date in various ISO8601 formats.

    Args:
        date_str: Date string in ISO8601 format

    Returns:
        datetime object with timezone info, or None if parsing fails
    """
    try:
        # AWS_CREDENTIAL_EXPIRATION can be in formats like:
        # - 2025-08-29T17:42:03+00:00 (with timezone)
        # - 2024-01-15T12:34:56Z (UTC)

        # Normalize Z timezone to +00:00 for fromisoformat
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"

        expiration_time = datetime.fromisoformat(date_str)

        # Ensure we have timezone info
        if expiration_time.tzinfo is None:
            expiration_time = expiration_time.replace(tzinfo=UTC)

        return expiration_time
    except ValueError:
        return None


def format_time_remaining(total_seconds: float) -> str:
    """Format time remaining in human-readable format.

    Args:
        total_seconds: Total seconds remaining

    Returns:
        Formatted string like "2 hours, 30 minutes" or "45 minutes"
    """
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)

    if hours > 0:
        hour_str = "1 hour" if hours == 1 else f"{hours} hours"
        return f"{hour_str}, {minutes} minutes" if minutes > 0 else hour_str
    else:
        return f"{minutes} minutes"


def check_aws_credentials():
    """Check if AWS credentials are set and valid."""
    # Check if AWS_CREDENTIAL_EXPIRATION is set
    expiration_str = os.environ.get("AWS_CREDENTIAL_EXPIRATION")

    if not expiration_str:
        print("❌ ERROR: AWS_CREDENTIAL_EXPIRATION is not set!")
        print_aws_login_instructions()
        return False

    # Parse the expiration time
    expiration_time = parse_aws_expiration_date(expiration_str)

    if expiration_time is None:
        print(f"⚠️  WARNING: Could not parse AWS_CREDENTIAL_EXPIRATION: {expiration_str}")
        print("Continuing anyway...")
        return True  # Don't fail, just warn

    # Check if expired
    current_time = datetime.now(UTC)

    if current_time >= expiration_time:
        print("❌ ERROR: AWS credentials have expired!")
        print(f"Expiration time: {expiration_str}")
        print_aws_login_instructions()
        return False

    # Calculate and display time remaining
    time_remaining = expiration_time - current_time
    total_seconds = time_remaining.total_seconds()

    print("✅ AWS credentials are valid")
    print(f"   Expires: {expiration_str}")
    print(f"   Time remaining: {format_time_remaining(total_seconds)}")

    # Warn if expiring soon (less than 1 hour)
    if total_seconds < 3600:
        print("⚠️  WARNING: Credentials expiring soon! Consider refreshing with 'aws sso login'")

    return True


def main():
    """Main entry point."""
    use_remote_data = os.environ.get("GRAPEVINE_LOCAL_REMOTE_DATA") is not None

    print("🔍 Checking development credentials...")
    print(f"   Mode: {'local_remote_data' if use_remote_data else 'local'}")
    print("")

    success = True

    # Only check AWS credentials in local_remote_data mode
    if use_remote_data:
        aws_success = check_aws_credentials()
        success = success and aws_success
    else:
        print("ℹ️  AWS credentials check skipped (local mode)")

    print("")
    if success:
        print("✅ All required credentials are valid")
    else:
        print("❌ Some credentials are missing or invalid")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
