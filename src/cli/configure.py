#!/usr/bin/env python3
"""Interactive CLI for configuring local development services."""

import sys

# ANSI color codes
RED = "\033[0;31m"
NC = "\033[0m"  # No Color


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{RED}Error: {text}{NC}")


def print_usage() -> None:
    """Print usage information."""
    print("Usage: mise configure <service>")
    print()
    print("Available services:")
    print("  slack  - Setup local Slack bot for development")
    print()


def main() -> None:
    """Main entry point for the CLI."""
    if len(sys.argv) < 2:
        print_error("No service specified")
        print()
        print_usage()
        sys.exit(1)

    service = sys.argv[1].lower()

    if service == "slack":
        # Import and run the Slack configure CLI
        from . import configure_slack

        configure_slack.main()
    else:
        print_error(f"Unknown service: {service}")
        print()
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print()
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
