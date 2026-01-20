#!/bin/sh

# Docker entrypoint script for Grapevine admin (Node.js + frontend)
# Replaces environment config placeholders with actual values at container startup

set -e

# Path to the environment config file (served by Express static files)
ENV_CONFIG_FILE="/app/admin-backend/dist/public/env-config.js"

echo "🔧 Configuring runtime environment variables..."

# Replace all placeholders with environment variables
# Map from VITE-prefixed environment variables to our runtime config
# If an environment variable is not set, the placeholder will remain
sed -i "s|__AMPLITUDE_API_KEY__|${VITE_AMPLITUDE_API_KEY:-__AMPLITUDE_API_KEY__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__NEW_RELIC_LICENSE_KEY__|${VITE_NEW_RELIC_LICENSE_KEY:-__NEW_RELIC_LICENSE_KEY__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__NEW_RELIC_APPLICATION_ID__|${VITE_NEW_RELIC_APPLICATION_ID:-__NEW_RELIC_APPLICATION_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__NEW_RELIC_ACCOUNT_ID__|${VITE_NEW_RELIC_ACCOUNT_ID:-__NEW_RELIC_ACCOUNT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__NEW_RELIC_TRUST_KEY__|${VITE_NEW_RELIC_TRUST_KEY:-__NEW_RELIC_TRUST_KEY__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__NEW_RELIC_AGENT_ID__|${VITE_NEW_RELIC_AGENT_ID:-__NEW_RELIC_AGENT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__WORKOS_CLIENT_ID__|${VITE_WORKOS_CLIENT_ID:-__WORKOS_CLIENT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__SSO_ALLOWED_PARENT_ORIGINS__|${VITE_SSO_ALLOWED_PARENT_ORIGINS:-__SSO_ALLOWED_PARENT_ORIGINS__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__WORKOS_API_HOSTNAME__|${VITE_WORKOS_API_HOSTNAME:-__WORKOS_API_HOSTNAME__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__POSTHOG_API_KEY__|${VITE_POSTHOG_API_KEY:-__POSTHOG_API_KEY__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__POSTHOG_HOST__|${VITE_POSTHOG_HOST:-__POSTHOG_HOST__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__POSTHOG_UI_HOST__|${VITE_POSTHOG_UI_HOST:-__POSTHOG_UI_HOST__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__BASE_DOMAIN__|${BASE_DOMAIN:-__BASE_DOMAIN__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__FRONTEND_URL__|${FRONTEND_URL:-__FRONTEND_URL__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__ENVIRONMENT__|${ENVIRONMENT:-production}|g" "$ENV_CONFIG_FILE"
sed -i "s|__MCP_BASE_URL__|${VITE_MCP_BASE_URL:-__MCP_BASE_URL__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__JIRA_APP_ID__|${VITE_JIRA_APP_ID:-__JIRA_APP_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__JIRA_APP_ENVIRONMENT_ID__|${VITE_JIRA_APP_ENVIRONMENT_ID:-__JIRA_APP_ENVIRONMENT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__CONFLUENCE_APP_ID__|${VITE_CONFLUENCE_APP_ID:-__CONFLUENCE_APP_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__CONFLUENCE_APP_ENVIRONMENT_ID__|${VITE_CONFLUENCE_APP_ENVIRONMENT_ID:-__CONFLUENCE_APP_ENVIRONMENT_ID__}|g" "$ENV_CONFIG_FILE"

# Escape '&' in URLs to prevent sed from interpreting them as pattern references
JIRA_URL_ESCAPED=$(printf '%s\n' "${VITE_JIRA_APP_INSTALLATION_URL:-__JIRA_APP_INSTALLATION_URL__}" | sed 's/&/\\&/g')
sed -i "s|__JIRA_APP_INSTALLATION_URL__|${JIRA_URL_ESCAPED}|g" "$ENV_CONFIG_FILE"
CONFLUENCE_URL_ESCAPED=$(printf '%s\n' "${VITE_CONFLUENCE_APP_INSTALLATION_URL:-__CONFLUENCE_APP_INSTALLATION_URL__}" | sed 's/&/\\&/g')
sed -i "s|__CONFLUENCE_APP_INSTALLATION_URL__|${CONFLUENCE_URL_ESCAPED}|g" "$ENV_CONFIG_FILE"
sed -i "s|__TRELLO_POWER_UP_API_KEY__|${VITE_TRELLO_POWER_UP_API_KEY:-__TRELLO_POWER_UP_API_KEY__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__INTERCOM_CLIENT_ID__|${VITE_INTERCOM_CLIENT_ID:-__INTERCOM_CLIENT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__SALESFORCE_CLIENT_ID__|${VITE_SALESFORCE_CLIENT_ID:-__SALESFORCE_CLIENT_ID__}|g" "$ENV_CONFIG_FILE"
sed -i "s|__GITLAB_CLIENT_ID__|${VITE_GITLAB_CLIENT_ID:-__GITLAB_CLIENT_ID__}|g" "$ENV_CONFIG_FILE"

echo "✅ Environment configuration complete"

# Debug: Show final config (remove sensitive values from logs)
echo "📋 Runtime configuration:"
sed 's/"[^"]*_KEY":[^,]*/"***_KEY":"***"/g; s/"[^"]*_API_KEY":[^,]*/"***_API_KEY":"***"/g' "$ENV_CONFIG_FILE"

# Start Node.js server
echo "🚀 Starting Node.js server..."
exec node admin-backend/dist/src/server.js