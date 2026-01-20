#!/usr/bin/env bash
# Wrapper script for backfill CLI - backwards compatibility alias for 'mise connector backfill'

set -euo pipefail

# Set AWS_REGION default if not provided
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Validate that tenant_id is provided
if [ -z "${usage_tenant_id:-}" ]; then
  echo "Error: --tenant-id is required"
  exit 1
fi

tenant_id="${usage_tenant_id}"

# Build arguments for connector CLI backfill command
args=("--tenant-id" "${tenant_id}")

# Add connector if provided
if [ -n "${usage_connector:-}" ]; then
  args+=("--connector" "${usage_connector}")
fi

# Add config file if provided
if [ -n "${usage_config_file:-}" ]; then
  args+=("--config-file" "${usage_config_file}")
fi

# Execute - now using connector CLI backfill command
exec uv run python -m connectors.cli backfill "${args[@]}"
