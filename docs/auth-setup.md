# Authentication Setup

This guide explains how to set up authentication for Grapevine. The system uses [WorkOS](https://workos.com/) as the authentication provider, which handles user management, SSO, and OAuth flows.

## Overview

Grapevine requires WorkOS for:

- **User Authentication**: Login/signup flows via AuthKit
- **Organization Management**: Multi-tenant organization support
- **MCP Server Security**: OAuth-based authentication for MCP protocol

> **Note**: WorkOS is currently the only supported authentication provider. Future versions may support alternative authentication methods.

## WorkOS Account Setup

### 1. Create a WorkOS Account

1. Sign up at [WorkOS](https://workos.com/). WorkOS offers a free tier that includes:
   - Up to 1 million monthly active users
   - Unlimited organizations
   - AuthKit (managed authentication UI)

2. Create a new project in the WorkOS dashboard

3. Note your **API Key** and **Client ID** from the project settings

### 2. Configure AuthKit

AuthKit provides a hosted authentication UI. To enable it:

1. Go to **Authentication** → **AuthKit** in the WorkOS dashboard
2. Enable AuthKit for your project
3. Configure your **Redirect URI(s)**:
   - Local development: `http://localhost:5173/callback`
   - Production: `https://your-domain.com/callback`
4. Enable **Dynamic Client Registration** under **Applications** → **Configuration**
   - This is required for MCP OAuth authentication
5. Copy your **AuthKit Domain** (looks like `https://your-project-12345.authkit.app`)

### 3. Configure Organizations (Multi-tenant)

If running in multi-tenant mode:

1. Go to **Organizations** in the WorkOS dashboard
2. Create organizations for each tenant
3. Note the **Organization ID** for each (used as `workos_org_id` in the tenants table)

## Environment Variables

### Required Variables

```bash
# WorkOS API credentials
WORKOS_API_KEY=sk_live_...        # From WorkOS dashboard → API Keys
WORKOS_CLIENT_ID=client_...       # From WorkOS dashboard → Configuration

# AuthKit configuration (for MCP server)
AUTHKIT_DOMAIN=https://your-project-12345.authkit.app
```

### Frontend Variables

```bash
# For the admin frontend (Vite)
VITE_WORKOS_CLIENT_ID=client_...
VITE_WORKOS_REDIRECT_URI=http://localhost:5173/callback
```

### Optional Variables

```bash
# Custom AuthKit base URL (if self-hosting AuthKit)
AUTHKIT_BASE_URL=https://custom-authkit.example.com

# MCP server base URL (for OAuth callback)
MCP_BASE_URL=http://localhost:8000
```

## MCP Server Authentication (AuthKit)

The MCP server uses AuthKit for OAuth-based authentication. This secures the MCP protocol endpoints.

### Configuration Options

#### Option A: Code-based Configuration (Default)

The MCP instance wires AuthKit automatically using config values:

```python
# src/mcp/mcp_instance.py
from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import AuthKitProvider
from src.utils.config import get_authkit_domain, get_mcp_base_url

authkit_domain = get_authkit_domain()  # e.g., https://your-project-12345.authkit.app
base_url = get_mcp_base_url()          # e.g., http://localhost:8000

auth = AuthKitProvider(authkit_domain=authkit_domain, base_url=base_url)
mcp = FastMCP("corporate-context", stateless_http=True, auth=auth)
```

Set these environment variables:

- `AUTHKIT_DOMAIN`: Your AuthKit domain
- `MCP_BASE_URL`: Externally reachable base URL of the MCP server (no trailing slash, don't include `/mcp`)

#### Option B: Environment-only Configuration

FastMCP can auto-create the provider via environment variables (no code changes):

```bash
FASTMCP_SERVER_AUTH=AUTHKIT
FASTMCP_SERVER_AUTH_AUTHKITPROVIDER_AUTHKIT_DOMAIN="https://your-project-12345.authkit.app"
FASTMCP_SERVER_AUTH_AUTHKITPROVIDER_BASE_URL="http://localhost:8000"
```

Then instantiate without passing an auth provider:

```python
from fastmcp import FastMCP
mcp = FastMCP(name="corporate-context")
```

## Testing Authentication Locally

### Start the MCP Server

```bash
python -m src.mcp.server --host 0.0.0.0 --port 8000
```

### Test with a FastMCP Client

```python
from fastmcp import Client
import asyncio

async def main():
    async with Client("http://localhost:8000/mcp/", auth="oauth") as client:
        assert await client.ping()

if __name__ == "__main__":
    asyncio.run(main())
```

The client will open a browser window for OAuth authentication if needed.

## Troubleshooting

### Common Issues

1. **"Invalid redirect URI" error**
   - Ensure your redirect URI is configured in WorkOS dashboard
   - Check that `VITE_WORKOS_REDIRECT_URI` matches exactly

2. **"Dynamic client registration disabled" error**
   - Enable Dynamic Client Registration in WorkOS under **Applications** → **Configuration**

3. **MCP authentication fails**
   - Verify `AUTHKIT_DOMAIN` is correct
   - Ensure `MCP_BASE_URL` is accessible from your browser

4. **"Organization not found" error**
   - Check that the organization exists in WorkOS
   - Verify the `workos_org_id` in your database matches

### Debugging

Check WorkOS logs in the dashboard under **Logs** for authentication events and errors.

## Security Considerations

- Never commit API keys to version control
- Use environment variables or secrets management for credentials
- In production, always use HTTPS for redirect URIs
- Rotate API keys periodically

## Additional Resources

- [WorkOS Documentation](https://workos.com/docs)
- [AuthKit Documentation](https://workos.com/docs/authkit)
- [FastMCP AuthKit Integration](https://gofastmcp.com/integrations/authkit)
- [WorkOS Pricing](https://workos.com/pricing)
