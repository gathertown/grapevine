# Admin Backend Scripts

This directory contains administrative scripts for managing the Grapevine backend.

## Notion CRM Backfill Script

### Overview

The `backfill-notion-crm.ts` script reads all provisioned tenants from the control database, fetches their organization details from WorkOS, and creates records in the Notion CRM database.

### Prerequisites

1. **Environment Variables**: Ensure the following are configured:
   - `CONTROL_DATABASE_URL` - Connection string for the control database
   - `WORKOS_API_KEY` - WorkOS API key for fetching organization details
   - `NOTION_CRM_TOKEN` - Notion integration token
   - `NOTION_CRM_DATABASE_ID` - Notion database ID for the CRM

2. **Notion Database Setup**: The Notion database should have the following properties:
   - `Tenant ID` (title) - Internal tenant identifier
   - `WorkOS Organization ID` (rich text)
   - `Organization Name` (rich text)
   - `Admin Emails` (rich text)
   - `Onboarding State` (select) - Options: started, onboarded, churned
   - `Slack Bot Configured` (checkbox)
   - `First Integration Connected` (checkbox)
   - `Connected Integrations` (multi-select)
   - `Requested Integrations` (multi-select)
   - `Created At` (date)
   - `Last Activity` (date)

### Usage

#### Dry Run (Recommended First)

Run in dry-run mode to see what would be created without making any changes:

```bash
# Using npm script (recommended)
cd js-services/admin-backend
yarn backfill-notion-crm:dry-run

# Or run directly with tsx
npx tsx scripts/backfill-notion-crm.ts --dry-run

# For a specific tenant only
npx tsx scripts/backfill-notion-crm.ts --dry-run --tenant-id abc123def456
```

#### Production Run

Once you've verified the dry-run output, run without the flag to actually create records:

```bash
# Using npm script (recommended) - all tenants
cd js-services/admin-backend
yarn backfill-notion-crm

# Or run directly with tsx
npx tsx scripts/backfill-notion-crm.ts

# For a specific tenant only
npx tsx scripts/backfill-notion-crm.ts --tenant-id abc123def456
```

#### Options

- `--dry-run` - Show what would be created without making any changes
- `--tenant-id <tenant_id>` - Process only a specific tenant by ID

### What It Does

1. **Ensures all required properties exist** in the Notion data source (creates missing properties automatically):
   - Tenant ID (title) - _Must already exist as the database's title property_
   - WorkOS Organization ID (rich_text)
   - Organization Name (rich_text)
   - Admin Emails (multi_select) - Each email shown as a separate tag
   - Onboarding State (select: started, onboarded, churned)
   - Slack Bot Configured (checkbox)
   - First Integration Connected (checkbox)
   - Connected Integrations (multi_select)
   - Requested Integrations (multi_select)
   - Created At (date)
   - Last Activity (date)
   - Onboarded At (date)
2. **Fetches all tenants** from the control database (`public.tenants` table)
3. **Filters for provisioned tenants** (skips pending/error states)
4. **Fetches organization details** from WorkOS API:
   - Organization name
   - All active user emails from the organization (stored in "Admin Emails" field)
5. **Checks tenant configuration** from SSM/Database to determine:
   - Which integrations are configured
   - Whether Slack bot is set up
6. **Creates or updates Notion CRM records**:
   - Checks if a record already exists for the tenant
   - If exists: Updates the record with current data
   - If not exists: Creates a new record with:
     - Tenant ID
     - WorkOS organization ID
     - Organization name
     - Admin emails (array of all active user emails from the organization)
     - Initial onboarding state: "started"
7. **Updates integration statuses** based on actual configuration:
   - Slack Bot Configured (if SLACK_BOT_TOKEN exists)
   - Connected Integrations (updates for each configured integration)
   - First Integration Connected (automatically set if any integration exists)
   - Onboarding State (automatically set to "onboarded" if Slack + 1 integration)

### Output

The script provides detailed logging:

- Progress for each tenant
- Success/failure status
- Summary statistics at the end

Example output:

```
Found 25 tenants
Processing tenant abc123...
✅ Successfully created Notion record for tenant abc123
...
================================================================================
Backfill Summary:
  Total tenants: 25
  Provisioned: 20
  Not provisioned: 5
  Skipped: 5
  Created: 18
  Failed: 2
================================================================================
```

### Error Handling

- **Duplicate records**: If a record already exists in Notion (same Tenant ID), the creation will fail gracefully
- **Missing WorkOS org**: Tenants whose organizations can't be found in WorkOS are skipped
- **Rate limiting**: The script includes a 100ms delay between each tenant to avoid rate limits

### Integration Detection

The script automatically detects which integrations are configured by checking tenant configuration values:

- **Slack**: Has `SLACK_BOT_TOKEN`
- **GitHub**: Has `GITHUB_TOKEN` and `GITHUB_SETUP_COMPLETE` = 'true'
- **Notion**: Has `NOTION_TOKEN` and `NOTION_COMPLETE` = 'true'
- **Linear**: Has `LINEAR_API_KEY`
- **Google Drive**: Has `GOOGLE_DRIVE_ADMIN_EMAIL` and `GOOGLE_DRIVE_SERVICE_ACCOUNT`
- **Google Email**: Has `GOOGLE_EMAIL_ADMIN_EMAIL` and `GOOGLE_EMAIL_SERVICE_ACCOUNT`
- **Salesforce**: Has `SALESFORCE_REFRESH_TOKEN` and `SALESFORCE_INSTANCE_URL`
- **HubSpot**: Has `HUBSPOT_COMPLETE` = 'true'
- **Jira**: Has `JIRA_CLOUD_ID` and `JIRA_WEBTRIGGER_BACKFILL_URL`
- **Confluence**: Not yet fully implemented

### Notes

- Only **provisioned** tenants are processed
- The script fetches **all active user emails** from WorkOS organization memberships (regardless of role)
- User emails are stored as multi-select tags in the "Admin Emails" field in Notion (each email is a separate tag)
- The script uses existing Notion CRM functions for consistency with live updates
- Integration statuses are determined by checking actual tenant configuration (SSM + Database)
- **Onboarding state is automatically calculated**: If tenant has Slack bot + at least 1 integration, they'll be marked as "onboarded"
