"""Health check registry and implementations for connector types."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from connectors.asana.client.asana_client_factory import get_asana_client_for_tenant
from connectors.fireflies.client.fireflies_client_factory import get_fireflies_client_for_tenant
from connectors.fireflies.client.fireflies_models import GetFirefliesTranscriptsReq
from connectors.zendesk.client.zendesk_factory import get_zendesk_client_for_tenant
from src.clients.attio.attio_client import get_attio_client_for_tenant
from src.clients.confluence import ConfluenceClient
from src.clients.gather import GatherClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.gong_factory import get_gong_client_for_tenant
from src.clients.google_drive import GoogleDriveClient
from src.clients.google_email import GoogleEmailClient
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.intercom import get_intercom_client_for_tenant
from src.clients.jira import JiraClient
from src.clients.linear_factory import get_linear_client_for_tenant
from src.clients.notion import NotionClient
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.slack import SlackClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.clients.trello import TrelloClient
from src.database.connector_installations import Connector
from src.utils.config import get_trello_power_up_api_key
from src.utils.tenant_config import get_tenant_config_value
from src.warehouses.snowflake_service import SnowflakeService


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    message: str


# Type for health check functions
HealthCheckFn = Callable[
    [str, Connector, SSMClient],
    Awaitable[HealthCheckResult],
]

# Registry of health checks by connector type
HEALTH_CHECKS: dict[str, HealthCheckFn] = {}


def register_health_check(connector_type: str) -> Callable[[HealthCheckFn], HealthCheckFn]:
    """Decorator to register a health check for a connector type."""

    def decorator(fn: HealthCheckFn) -> HealthCheckFn:
        HEALTH_CHECKS[connector_type] = fn
        return fn

    return decorator


async def run_health_check(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Run health check for a connector, returning appropriate result."""
    # Skip pending/disconnected connectors
    if connector.status in ("pending", "disconnected"):
        return HealthCheckResult(healthy=False, message=f"Skipped ({connector.status})")

    # Look up health check in registry
    check_fn = HEALTH_CHECKS.get(connector.type)
    if check_fn is None:
        return HealthCheckResult(healthy=False, message="Not implemented")

    try:
        return await check_fn(tenant_id, connector, ssm_client)
    except Exception as e:
        return HealthCheckResult(healthy=False, message=str(e))


# --- Health Check Implementations ---


@register_health_check("github")
async def check_github(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check GitHub connector health by verifying API access."""
    client = await get_github_client_for_tenant(tenant_id, ssm_client)

    if client.is_app_authenticated():
        repos = client.get_installation_repositories()
        return HealthCheckResult(healthy=True, message=f"App: {len(repos)} repos")
    else:
        orgs = list(client.get_user_organizations())
        return HealthCheckResult(healthy=True, message=f"PAT: {len(orgs)} orgs")


@register_health_check("slack")
async def check_slack(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Slack connector health by calling auth.test."""
    token = await ssm_client.get_slack_token(tenant_id)
    if not token:
        return HealthCheckResult(healthy=False, message="No token found")

    client = SlackClient(token)
    auth_info = client.auth_test()
    team = auth_info.get("team", "unknown")
    return HealthCheckResult(healthy=True, message=f"Team: {team}")


@register_health_check("linear")
async def check_linear(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Linear connector health by fetching teams."""
    async with tenant_db_manager.acquire_pool(tenant_id) as db_pool:
        client = await get_linear_client_for_tenant(tenant_id, ssm_client, db_pool)
        teams = client.get_public_teams()
        return HealthCheckResult(healthy=True, message=f"{len(teams)} teams")


@register_health_check("notion")
async def check_notion(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Notion connector health by getting bot info."""
    token = await ssm_client.get_notion_token(tenant_id)
    if not token:
        return HealthCheckResult(healthy=False, message="No token found")

    client = NotionClient(token)
    bot_info = client.get_bot_info()
    bot_name = bot_info.get("name", "unknown")
    return HealthCheckResult(healthy=True, message=f"Bot: {bot_name}")


@register_health_check("jira")
async def check_jira(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Jira connector health by calling myself endpoint."""
    token = await ssm_client.get_jira_system_oauth_token(tenant_id)
    if not token:
        return HealthCheckResult(healthy=False, message="No token found")

    cloud_id = await get_tenant_config_value("JIRA_CLOUD_ID", tenant_id)
    if not cloud_id:
        return HealthCheckResult(healthy=False, message="No cloud_id configured")

    client = JiraClient(forge_oauth_token=token, cloud_id=cloud_id)
    # Use _make_request directly for /myself endpoint
    user_info = client._make_request("myself")
    display_name = user_info.get("displayName", "unknown")
    return HealthCheckResult(healthy=True, message=f"User: {display_name}")


@register_health_check("confluence")
async def check_confluence(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Confluence connector health by calling user/current endpoint."""
    token = await ssm_client.get_confluence_system_oauth_token(tenant_id)
    if not token:
        return HealthCheckResult(healthy=False, message="No token found")

    cloud_id = await get_tenant_config_value("CONFLUENCE_CLOUD_ID", tenant_id)
    if not cloud_id:
        return HealthCheckResult(healthy=False, message="No cloud_id configured")

    client = ConfluenceClient(forge_oauth_token=token, cloud_id=cloud_id)
    # Use _make_request for user/current endpoint
    user_info = client._make_request("user/current")
    display_name = user_info.get("publicName", "unknown")
    return HealthCheckResult(healthy=True, message=f"User: {display_name}")


@register_health_check("hubspot")
async def check_hubspot(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check HubSpot connector health by getting deal pipelines."""
    async with tenant_db_manager.acquire_pool(tenant_id) as db_pool:
        client = await get_hubspot_client_for_tenant(tenant_id, ssm_client, db_pool)
        pipelines = await client.get_pipelines("deals")
        return HealthCheckResult(healthy=True, message=f"{len(pipelines)} pipelines")


@register_health_check("google_drive")
async def check_google_drive(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Google Drive connector health by verifying drive and admin API access."""
    admin_email = await ssm_client.get_google_drive_admin_email(tenant_id)
    if not admin_email:
        return HealthCheckResult(healthy=False, message="No admin email configured")

    client = GoogleDriveClient(tenant_id=tenant_id, admin_email=admin_email, ssm_client=ssm_client)

    # Test drive.readonly scope - get info about the drive
    drive_service = await client._get_drive_service()
    about = drive_service.about().get(fields="user").execute()
    drive_user = about.get("user", {}).get("emailAddress", "unknown")

    # Test admin.directory.user.readonly scope - list users (limit 1)
    admin_service = await client._get_admin_service()
    domain = admin_email.split("@")[1]
    admin_service.users().list(domain=domain, maxResults=1).execute()

    return HealthCheckResult(healthy=True, message=f"Drive: {drive_user}")


@register_health_check("gather")
async def check_gather(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Gather connector health by fetching space info."""
    api_key = await ssm_client.get_gather_api_key(tenant_id)
    if not api_key:
        return HealthCheckResult(healthy=False, message="No API key found")

    client = GatherClient(api_key=api_key)
    # Use the connector's external_id as space_id
    space_id = connector.external_id
    # get_space validates API key and space access
    space_info = client.get_space(space_id)
    if space_info.get("exists"):
        return HealthCheckResult(healthy=True, message="Space exists")
    return HealthCheckResult(healthy=False, message="Space not found")


@register_health_check("asana")
async def check_asana(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Asana connector health by fetching workspace info."""
    client = await get_asana_client_for_tenant(tenant_id, ssm_client)
    async with client:
        # Use the connector's external_id as workspace_gid
        workspace_gid = connector.external_id
        workspace = await client.get_workspace(workspace_gid)
        return HealthCheckResult(healthy=True, message=f"Workspace: {workspace.name}")


@register_health_check("google_email")
async def check_google_email(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Google Email connector health by verifying gmail and admin API access."""
    admin_email = await ssm_client.get_google_email_admin_email(tenant_id)
    if not admin_email:
        return HealthCheckResult(healthy=False, message="No admin email configured")

    client = GoogleEmailClient(tenant_id=tenant_id, admin_email=admin_email, ssm_client=ssm_client)

    # Test gmail.readonly scope - get user profile
    email_service = await client._get_email_service()
    profile = email_service.users().getProfile(userId="me").execute()
    email_address = profile.get("emailAddress", "unknown")

    # Test admin.directory.user.readonly scope - list users (limit 1)
    admin_service = await client._get_admin_service()
    domain = admin_email.split("@")[1]
    admin_service.users().list(domain=domain, maxResults=1).execute()

    return HealthCheckResult(healthy=True, message=f"Email: {email_address}")


@register_health_check("trello")
async def check_trello(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Trello connector health by fetching current member info."""
    api_key = get_trello_power_up_api_key()
    if not api_key:
        return HealthCheckResult(healthy=False, message="No API key configured")

    api_token = await ssm_client.get_trello_token(tenant_id)
    if not api_token:
        return HealthCheckResult(healthy=False, message="No token found")

    client = TrelloClient(api_key=api_key, api_token=api_token)
    member = client.get_member("me")
    username = member.get("username", "unknown")
    return HealthCheckResult(healthy=True, message=f"User: {username}")


@register_health_check("zendesk")
async def check_zendesk(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Zendesk connector health by fetching current user info."""
    client = await get_zendesk_client_for_tenant(tenant_id, ssm_client)
    async with client:
        user_info = await client._get("/users/me")
        user = user_info.get("user", {})
        name = user.get("name", "unknown")
        return HealthCheckResult(healthy=True, message=f"User: {name}")


@register_health_check("gong")
async def check_gong(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Gong connector health by fetching workspaces."""
    client = await get_gong_client_for_tenant(tenant_id, ssm_client)
    async with client:
        workspaces = await client.get_workspaces()
        return HealthCheckResult(healthy=True, message=f"{len(workspaces)} workspaces")


@register_health_check("intercom")
async def check_intercom(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Intercom connector health by fetching app info."""
    client = await get_intercom_client_for_tenant(tenant_id, ssm_client)
    me_info = client.get_me()
    app_name = me_info.get("app", {}).get("name", "unknown")
    return HealthCheckResult(healthy=True, message=f"App: {app_name}")


@register_health_check("salesforce")
async def check_salesforce(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Salesforce connector health by verifying API access."""
    async with tenant_db_manager.acquire_pool(tenant_id) as db_pool:
        client = await get_salesforce_client_for_tenant(tenant_id, ssm_client, db_pool)
        try:
            # Simple query to verify access - get org limits (lightweight API call)
            await client._make_request("GET", "/limits")
            return HealthCheckResult(healthy=True, message=f"Org: {connector.external_id}")
        finally:
            await client.close()


@register_health_check("fireflies")
async def check_fireflies(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Fireflies connector health by fetching transcripts."""
    client = await get_fireflies_client_for_tenant(tenant_id, ssm_client)
    async with client:
        # Fetch a batch of 1 transcript to verify API access
        req = GetFirefliesTranscriptsReq(from_date=None, to_date=None, page_size=1)
        async for transcripts in client.get_transcripts(req):
            return HealthCheckResult(
                healthy=True, message=f"Found a transcript: {len(transcripts)}"
            )
        # If no transcripts, API still worked
        return HealthCheckResult(healthy=True, message="Found 0 transcripts")


@register_health_check("snowflake")
async def check_snowflake(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Snowflake connector health by verifying OAuth token and API access."""
    service = SnowflakeService()
    try:
        # This validates the token and refreshes if needed
        token, account_identifier = await service.get_valid_oauth_token(tenant_id)

        # Execute a simple query to verify full connectivity
        await service.execute_sql(tenant_id, "SELECT CURRENT_USER()")

        # Extract username from result if available
        username = token.username or account_identifier
        return HealthCheckResult(healthy=True, message=f"User: {username}")
    finally:
        await service.close()


@register_health_check("attio")
async def check_attio(
    tenant_id: str,
    connector: Connector,
    ssm_client: SSMClient,
) -> HealthCheckResult:
    """Check Attio connector health by fetching workspace members."""
    client = await get_attio_client_for_tenant(tenant_id, ssm_client)
    members = client.get_workspace_members()
    return HealthCheckResult(healthy=True, message=f"{len(members)} members")
