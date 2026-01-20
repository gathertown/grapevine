# Grapevine Admin Frontend

The admin frontend is a React + Vite application that provides a web interface for configuring and onboarding Grapevine data sources. Part of the Grapevine multi-tenant knowledge platform.

## Features

- **Organization Setup**: Configure organization details and authentication
- **Data Source Configuration**: Set up GitHub, Slack, Linear, Notion, Google Drive, HubSpot, and Jira integrations
- **Webhook Configuration**: Configure webhooks for real-time data ingestion
- **Icon Generation**: Generate company icons and branding
- **Multi-tenant Support**: Handle multiple organizations and workspaces

## Development

This service is part of the js-services workspace. Run commands from the workspace root:

```bash
# Install dependencies (from js-services/)
npm install

# Start development server
npm run dev --workspace=admin-frontend

# Build for production
npm run build --workspace=admin-frontend

# Run linting
npm run lint --workspace=admin-frontend
```

## Technology Stack

- **React 19**: Modern React with concurrent features
- **Vite**: Fast development and build tooling
- **TypeScript**: Type-safe development
- **AuthKit**: WorkOS authentication integration
- **CSS Modules**: Scoped styling

## Configuration

The frontend communicates with the admin backend service and requires proper configuration of:

- WorkOS authentication
- Backend API endpoints
- Organization management features

### Environment Variables

Create a `.env.local` file in the project root with the following variables:

```env
# WorkOS Configuration
VITE_WORKOS_CLIENT_ID=client_01H1NCC459Y9PMCA2THECKM2YK
VITE_WORKOS_API_HOSTNAME=api.workos.com
VITE_WORKOS_REDIRECT_URI=http://localhost:3000

# Analytics
VITE_AMPLITUDE_API_KEY=your_amplitude_key

# New Relic Browser Monitoring (auto-enabled when all vars are set)
VITE_NEW_RELIC_LICENSE_KEY=your_new_relic_license_key
VITE_NEW_RELIC_APPLICATION_ID=your_application_id
VITE_NEW_RELIC_ACCOUNT_ID=your_account_id
VITE_NEW_RELIC_TRUST_KEY=your_trust_key
VITE_NEW_RELIC_AGENT_ID=your_agent_id

# SSO Configuration
VITE_SSO_ALLOWED_PARENT_ORIGINS=https://app.v2.gather.town,https://staging.v2.gather.town
```

#### SSO Environment Variables

- `VITE_SSO_ALLOWED_PARENT_ORIGINS`: Comma-separated list of allowed parent window origins for popup-based SSO authentication. These are the domains from which the admin frontend can receive authentication grants via postMessage. Defaults to `https://app.v2.gather.town` if not specified.
