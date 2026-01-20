#!/usr/bin/env python
"""
Generate a report classifying WorkOS organizations by their usage status.

This script:
1. Enumerates all WorkOS organizations
2. Classifies them into buckets:
   - "launched": organizations with ingest_artifacts in their database
   - "failure to launch": organizations with a name but no ingest_artifacts
   - "ignore": organizations without name or with only test users (@gmail.com/@gather.town)
3. Prints detailed report for launched/failure to launch orgs

Usage:
    python scripts/workos_organization_report.py
    python scripts/workos_organization_report.py --created-after 2024-01-01
    python scripts/workos_organization_report.py --created-before 2024-12-31
    python scripts/workos_organization_report.py --created-after 2024-01-01 --created-before 2024-12-31
"""

import argparse
import asyncio
import csv
import logging
import sys
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from workos import WorkOSClient

from src.utils.config import get_config_value, get_control_database_url

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def initialize_workos() -> WorkOSClient:
    """Initialize WorkOS client using environment variables."""
    api_key = get_config_value("WORKOS_API_KEY")
    client_id = get_config_value("WORKOS_CLIENT_ID")

    if not api_key:
        raise ValueError("WORKOS_API_KEY environment variable is required")
    if not client_id:
        raise ValueError("WORKOS_CLIENT_ID environment variable is required")

    return WorkOSClient(api_key=api_key, client_id=client_id)


def fetch_all_organizations(workos_client: WorkOSClient) -> list:
    """Fetch all WorkOS organizations using pagination.

    Args:
        workos_client: Initialized WorkOS client

    Returns:
        List of all organization objects
    """
    all_orgs = []
    after = None
    page_count = 0

    while True:
        page_count += 1
        logger.info(f"Fetching organizations page {page_count}...")

        # Fetch organizations with pagination
        if after:
            organizations = workos_client.organizations.list_organizations(limit=100, after=after)
        else:
            organizations = workos_client.organizations.list_organizations(limit=100)

        page_orgs = list(organizations.data)
        all_orgs.extend(page_orgs)

        logger.info(f"Page {page_count}: Retrieved {len(page_orgs)} organizations")

        # Check if there are more pages
        if not organizations.list_metadata or not organizations.list_metadata.after:
            break

        after = organizations.list_metadata.after

    logger.info(f"Fetched {len(all_orgs)} total organizations across {page_count} pages")
    return all_orgs


async def get_all_tenants() -> dict[str, str]:
    """Get mapping of WorkOS org IDs to internal tenant IDs from control database.

    Returns:
        Dict mapping workos_org_id -> tenant_id for provisioned tenants
    """
    control_db_url = get_control_database_url()

    conn = await asyncpg.connect(control_db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT workos_org_id, id as tenant_id
            FROM public.tenants
            WHERE workos_org_id IS NOT NULL
              AND state = 'provisioned'
            """
        )
        return {row["workos_org_id"]: row["tenant_id"] for row in rows}
    finally:
        await conn.close()


def get_tenant_database_url(tenant_id: str) -> str:
    """Get database URL for a specific tenant using global environment variables."""
    # Get tenant database credentials from environment (same as migrations CLI)
    pg_host = get_config_value("PG_TENANT_DATABASE_HOST")
    pg_port = get_config_value("PG_TENANT_DATABASE_PORT", "5432")
    pg_username = get_config_value("PG_TENANT_DATABASE_ADMIN_USERNAME")
    pg_password = get_config_value("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    if not all([pg_host, pg_username, pg_password]):
        raise ValueError(
            "Missing tenant database credentials. Set PG_TENANT_DATABASE_HOST, "
            "PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
        )

    # Follow migrations CLI pattern: db_{tenant_id}
    db_name = f"db_{tenant_id}"

    return f"postgresql://{pg_username}:{pg_password}@{pg_host}:{pg_port}/{db_name}"


async def get_tenant_data(tenant_id: str) -> dict:
    """Get tenant data including ingest artifacts count and configuration values.

    Args:
        tenant_id: The tenant ID to query

    Returns:
        Dict containing ingest_count, allow_data_sharing, has_seen_privacy_screen
    """
    result = {"ingest_count": 0, "allow_data_sharing": None, "has_seen_privacy_screen": None}

    try:
        db_url = get_tenant_database_url(tenant_id)
        logger.info(f"Connecting to tenant database for {tenant_id}...")
        conn = await asyncpg.connect(db_url)
        logger.info(f"Successfully connected to tenant database for {tenant_id}")

        try:
            # Count ingest artifacts
            row = await conn.fetchrow("SELECT COUNT(*) as count FROM public.ingest_artifact")
            result["ingest_count"] = row["count"] if row else 0

            # Get configuration values
            config_rows = await conn.fetch("""
                SELECT key, value FROM public.config
                WHERE key IN ('ALLOW_DATA_SHARING_FOR_IMPROVEMENTS', 'HAS_SEEN_DATA_PRIVACY_SCREEN', 'HAS_COMPLETED_ONBOARDING_SURVEY')
            """)

            # Convert to dict for easy lookup
            config_dict = {row["key"]: row["value"] for row in config_rows}
            result["allow_data_sharing"] = config_dict.get("ALLOW_DATA_SHARING_FOR_IMPROVEMENTS")
            result["has_seen_privacy_screen"] = config_dict.get("HAS_SEEN_DATA_PRIVACY_SCREEN")
            result["has_completed_onboarding_survey"] = config_dict.get(
                "HAS_COMPLETED_ONBOARDING_SURVEY"
            )

            logger.info(
                f"Tenant {tenant_id}: {result['ingest_count']:,} artifacts, "
                f"data_sharing: {result['allow_data_sharing']}, "
                f"privacy_screen: {result['has_seen_privacy_screen']}, "
                f"onboarding_survey: {result['has_completed_onboarding_survey']}"
            )

            return result
        finally:
            await conn.close()

    except Exception as e:
        logger.warning(f"Could not query tenant data for {tenant_id}: {e}")
        return result


def is_test_user_email(email: str) -> bool:
    """Check if an email is from a test domain."""
    if not email:
        return True  # Consider empty emails as test users

    test_domains = [
        "@gmail.com",
        "@gather.town",
        "@mailinator.com",
        "@davidrorr.com",
        "@testbridge.io",
        "@theonlyjohnny.sh",
        "@chandlerroth.com",
    ]
    return any(email.lower().endswith(domain) for domain in test_domains)


def classify_organization(org, org_members: list, has_ingest_artifacts: bool) -> str:
    """Classify an organization into one of three buckets.

    Args:
        org: WorkOS organization object
        org_members: List of organization membership objects
        has_ingest_artifacts: Whether the org has any ingest artifacts

    Returns:
        Classification: "launched", "failure to launch", or "ignore"
    """
    # Check if organization has a name
    if not org.name or org.name.strip() == "":
        return "ignore"

    # Check if organization has no members
    if not org_members or len(org_members) == 0:
        return "ignore"

    # Check if all users are test users (have test domains like @gmail.com, @gather.town, @mailinator.com, @davidrorr.com)
    # Special case: if there are 5+ Gather users, it's likely the real Gather org, so don't ignore
    gather_users = [
        member
        for member in org_members
        if getattr(member["user"], "email", "").lower().endswith("@gather.town")
    ]

    all_test_users = all(
        is_test_user_email(getattr(member["user"], "email", "")) for member in org_members
    )

    if all_test_users and len(gather_users) < 5:
        return "ignore"

    # If organization has ingest artifacts, it's launched
    if has_ingest_artifacts:
        return "launched"

    # Otherwise, it's a failure to launch
    return "failure to launch"


async def generate_report(created_after: str = None, created_before: str = None):
    """Generate and print the WorkOS organization report.

    Args:
        created_after: Optional date string (YYYY-MM-DD) to filter organizations created after this date
        created_before: Optional date string (YYYY-MM-DD) to filter organizations created before this date
    """
    logger.info("Initializing WorkOS client...")
    workos_client = initialize_workos()

    logger.info("Fetching tenant mappings from control database...")
    tenant_mappings = await get_all_tenants()
    logger.info(f"Found {len(tenant_mappings)} provisioned tenants")

    logger.info("Fetching WorkOS organizations...")
    org_data = fetch_all_organizations(workos_client)

    # Filter by creation date if specified
    if created_after or created_before:
        filter_after = None
        filter_before = None

        # Parse filter dates
        try:
            if created_after:
                filter_after = datetime.strptime(created_after, "%Y-%m-%d").replace(tzinfo=UTC)
            if created_before:
                filter_before = datetime.strptime(created_before, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as e:
            logger.error(f"Invalid date format. Use YYYY-MM-DD format. Error: {e}")
            sys.exit(1)

        # Log filtering criteria
        filter_msg = []
        if created_after:
            filter_msg.append(f"after {created_after}")
        if created_before:
            filter_msg.append(f"before {created_before}")
        logger.info(f"Filtering organizations created {' and '.join(filter_msg)}")

        original_count = len(org_data)
        filtered_orgs = []

        for org in org_data:
            if org.created_at:
                # Parse WorkOS datetime - handle both with and without 'Z' suffix
                org_date_str = str(org.created_at)
                if org_date_str.endswith("Z"):
                    org_date_str = org_date_str[:-1] + "+00:00"
                elif "+" not in org_date_str and "T" in org_date_str:
                    org_date_str += "+00:00"

                try:
                    org_created_at = datetime.fromisoformat(org_date_str)

                    # Apply both filters if specified
                    include_org = True
                    if filter_after and org_created_at <= filter_after:
                        include_org = False
                    if filter_before and org_created_at >= filter_before:
                        include_org = False

                    if include_org:
                        filtered_orgs.append(org)

                except ValueError as e:
                    logger.warning(
                        f"Could not parse creation date for org {org.id}: {org_date_str}, error: {e}"
                    )
                    # Include orgs with unparseable dates to be safe
                    filtered_orgs.append(org)
            else:
                # Include orgs without creation dates to be safe
                filtered_orgs.append(org)

        org_data = filtered_orgs
        logger.info(f"Filtered from {original_count} to {len(org_data)} organizations")

    # Classification buckets
    launched = []
    failure_to_launch = []
    ignored_count = 0

    logger.info(f"Processing {len(org_data)} organizations...")

    for org in org_data:
        logger.info(f"Processing organization: {org.name} (ID: {org.id})")

        # Get organization members using WorkOS user management API
        try:
            memberships_response = workos_client.user_management.list_organization_memberships(
                organization_id=org.id,
                statuses=["active"],  # Only get active memberships
                limit=100,  # Increased limit to get more members
            )
            memberships = list(memberships_response.data)

            # Fetch user details for each membership
            org_members = []
            for membership in memberships:
                try:
                    user = workos_client.user_management.get_user(membership.user_id)
                    # Create a combined object with both membership and user data
                    combined_member = {
                        "membership": membership,
                        "user": user,
                    }
                    org_members.append(combined_member)
                except Exception as e:
                    logger.warning(
                        f"Could not fetch user {membership.user_id} for org {org.id}: {e}"
                    )
                    continue

            logger.debug(f"Found {len(org_members)} active members for org {org.id}")
        except Exception as e:
            logger.warning(f"Could not fetch members for org {org.id}: {e}")
            org_members = []

        # Check if organization has ingest artifacts and get config data
        has_ingest_artifacts = False
        tenant_id = tenant_mappings.get(org.id)
        tenant_data = {
            "ingest_count": 0,
            "allow_data_sharing": None,
            "has_seen_privacy_screen": None,
        }

        if tenant_id:
            tenant_data = await get_tenant_data(tenant_id)
            has_ingest_artifacts = tenant_data["ingest_count"] > 0

        # Classify organization
        classification = classify_organization(org, org_members, has_ingest_artifacts)

        if classification == "ignore":
            ignored_count += 1
            if not org.name or org.name.strip() == "":
                reason = "No organization name"
            elif not org_members or len(org_members) == 0:
                reason = "No active members"
            else:
                gather_count = len(
                    [
                        member
                        for member in org_members
                        if getattr(member["user"], "email", "").lower().endswith("@gather.town")
                    ]
                )
                if gather_count > 0:
                    reason = f"All {len(org_members)} users have test email domains ({gather_count} @gather.town, {len(org_members) - gather_count} @gmail.com)"
                else:
                    reason = f"All {len(org_members)} users have test email domains"
            logger.info(f"IGNORED: {org.name or 'Unnamed Organization'} - {reason}")
        elif classification == "launched":
            launched.append(
                {
                    "org": org,
                    "tenant_id": tenant_id,
                    "member_count": len(org_members),
                    "ingest_count": tenant_data["ingest_count"],
                    "allow_data_sharing": tenant_data["allow_data_sharing"],
                    "has_seen_privacy_screen": tenant_data["has_seen_privacy_screen"],
                    "members": org_members,
                }
            )
        else:  # failure to launch
            failure_to_launch.append(
                {
                    "org": org,
                    "tenant_id": tenant_id,
                    "member_count": len(org_members),
                    "ingest_count": tenant_data["ingest_count"],
                    "allow_data_sharing": tenant_data["allow_data_sharing"],
                    "has_seen_privacy_screen": tenant_data["has_seen_privacy_screen"],
                    "members": org_members,
                }
            )

    # Generate CSV report
    csv_output = StringIO()
    csv_writer = csv.writer(csv_output)

    # Write CSV header
    csv_writer.writerow(
        [
            "Classification",
            "Organization Name",
            "WorkOS ID",
            "Organization Created",
            "Tenant ID",
            "Member Count",
            "Ingest Artifacts Count",
            "Allow Data Sharing",
            "Has Seen Privacy Screen",
            "User Names",
            "User Emails",
        ]
    )

    # Write launched organizations
    for item in sorted(launched, key=lambda x: int(x["ingest_count"]), reverse=True):  # type: ignore
        org = item["org"]  # type: ignore

        # Collect user information
        user_names = []
        user_emails = []

        if item["members"]:  # type: ignore
            for member in item["members"]:  # type: ignore
                user = member["user"]

                first_name = getattr(user, "first_name", "")
                last_name = getattr(user, "last_name", "")
                name = f"{first_name} {last_name}".strip() or "No name"
                email = getattr(user, "email", "No email")

                user_names.append(name)
                user_emails.append(email)

        csv_writer.writerow(
            [
                "launched",
                org.name,
                org.id,
                str(org.created_at),
                item["tenant_id"],
                item["member_count"],
                item["ingest_count"],
                item["allow_data_sharing"],
                item["has_seen_privacy_screen"],
                "; ".join(user_names),
                "; ".join(user_emails),
            ]
        )

    # Write failure to launch organizations
    for item in sorted(failure_to_launch, key=lambda x: int(x["member_count"]), reverse=True):  # type: ignore
        org = item["org"]  # type: ignore

        # Collect user information
        user_names = []
        user_emails = []

        if item["members"]:  # type: ignore
            for member in item["members"]:  # type: ignore
                user = member["user"]

                first_name = getattr(user, "first_name", "")
                last_name = getattr(user, "last_name", "")
                name = f"{first_name} {last_name}".strip() or "No name"
                email = getattr(user, "email", "No email")

                user_names.append(name)
                user_emails.append(email)

        csv_writer.writerow(
            [
                "failure to launch",
                org.name,
                org.id,
                str(org.created_at),
                item["tenant_id"] or "Not provisioned",
                item["member_count"],
                item["ingest_count"],
                item["allow_data_sharing"],
                item["has_seen_privacy_screen"],
                "; ".join(user_names),
                "; ".join(user_emails),
            ]
        )

    # Print summary statistics
    print("\n" + "=" * 80)
    print("WORKOS ORGANIZATION REPORT SUMMARY")
    print("=" * 80)
    print(f"Total organizations processed: {len(org_data)}")
    print(f"Ignored organizations: {ignored_count}")
    print(f"Launched organizations: {len(launched)}")
    print(f"Failure to launch organizations: {len(failure_to_launch)}")
    print()

    # Print CSV data
    print("CSV Report:")
    print("=" * 80)
    print(csv_output.getvalue())

    print("=" * 80)
    print("Report completed successfully!")


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate a WorkOS organization report with classification buckets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate report for all organizations
  python scripts/workos_organization_report.py

  # Generate report for organizations created after 2024-01-01
  python scripts/workos_organization_report.py --created-after 2024-01-01

  # Generate report for organizations created before 2024-12-31
  python scripts/workos_organization_report.py --created-before 2024-12-31

  # Generate report for organizations created in a specific date range
  python scripts/workos_organization_report.py --created-after 2024-01-01 --created-before 2024-12-31
        """,
    )
    parser.add_argument(
        "--created-after",
        type=str,
        help="Only include organizations created after this date (format: YYYY-MM-DD)",
        metavar="YYYY-MM-DD",
    )
    parser.add_argument(
        "--created-before",
        type=str,
        help="Only include organizations created before this date (format: YYYY-MM-DD)",
        metavar="YYYY-MM-DD",
    )

    args = parser.parse_args()

    # Validate required environment variables
    required_env_vars = [
        "WORKOS_API_KEY",
        "WORKOS_CLIENT_ID",
        "CONTROL_DATABASE_URL",
        "PG_TENANT_DATABASE_HOST",
        "PG_TENANT_DATABASE_ADMIN_USERNAME",
        "PG_TENANT_DATABASE_ADMIN_PASSWORD",
    ]

    missing_vars = [var for var in required_env_vars if not get_config_value(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please ensure the required environment variables are set.")
        sys.exit(1)

    try:
        await generate_report(created_after=args.created_after, created_before=args.created_before)
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
