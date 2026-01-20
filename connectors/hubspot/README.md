# HubSpot Connector App

This directory contains the HubSpot OAuth app configuration for the Grapevine integration.

## HubSpot Account Types

Understanding the different HubSpot account types is essential for development:

### 1. Developer Account

- Created at [developers.hubspot.com](https://developers.hubspot.com)
- Purpose: Build and manage apps (OAuth apps, marketplace apps, private apps)
- Used for:
  - Creating apps that provide Client ID/Secret
  - Managing projects with the HubSpot CLI
  - Configuring app distribution (private vs marketplace)
- **Note:** This is NOT a CRM account - it's your "app factory"

### 2. Standard Account (CRM Portal)

- Regular HubSpot account used by companies (Sales Hub, Marketing Hub, etc.)
- Purpose: Use HubSpot CRM for contacts, deals, workflows
- This is where apps get installed by end users
- Think of this as the "customer" or "tenant" account

### 3. Developer Test Account

- Free sandbox CRM bundled with your Developer Account
- Purpose: Safe testing environment for your apps
- Features:
  - Full CRM features for free (testing only)
  - Doesn't expire
  - Multiple test accounts can be created
  - Doesn't count against install caps (e.g., 25 unlisted marketplace installs)

### How They Work Together

1. **Create the app** in your Developer Account
2. **Install the app** into a Standard Account or Developer Test Account
3. **OAuth handshake** provides tokens to access the CRM APIs

## Development Workflow

### Prerequisites

Install the HubSpot CLI:

```bash
npm install -g @hubspot/cli
```

### Initial Setup

1. Authenticate with your Developer Account:

```bash
hs auth
```

2. Initialize the project (if not already done):

```bash
hs project create
```

### Making Changes

When modifying the app configuration:

1. Edit the app configuration files in connector-apps/hubspot/local/src/app/`
2. Deploy changes to HubSpot:

```bash
hs project upload
```

**Important:** All app configuration changes should be made in code, not through the HubSpot UI. This ensures our configuration is version controlled and reproducible.

**Important:** Github actions handle the deployment of staging and production apps, changes must be replicated to those environment folders

### HubSpot CLI Reference

For detailed CLI documentation, see: [HubSpot CLI Reference](https://developers.hubspot.com/docs/developer-tooling/local-development/hubspot-cli/reference)

## App Configuration

The app is configured as an **unlisted marketplace app** which provides:

- OAuth 2.0 authentication flow
- Refresh tokens for long-lived access
- Full API access including webhooks
- No admin allowlist requirements
- Up to 25 installs before requiring marketplace listing

### Key Files

- `hsproject.json` - Project configuration linking this directory to your HubSpot app
- `src/app/app-hsmeta.json` - App metadata and configuration

### OAuth Redirect URLs

OAuth redirect URLs must use HTTPS, with the exception of `http://localhost` for local testing. Configure these in the app settings based on your environment needs.

## TODO

- [ ] Create GitHub Action to run `hs project upload` when changes are merged to `connector-apps/hubspot/`
- [ ] Document app-hsmeta.json fields and their purposes
- [ ] Add environment-specific configuration guidance
