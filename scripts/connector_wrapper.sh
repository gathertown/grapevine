#!/usr/bin/env bash
# Wrapper script for connector CLI

set -euo pipefail

# Set AWS_REGION default if not provided
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Get subcommand from usage_subcommand (defaults to stats)
subcommand="${usage_subcommand:-stats}"

# Build arguments for connector CLI - pass through all remaining arguments
args=()

# Add tenant-id if provided
if [ -n "${usage_tenant_id:-}" ]; then
  args+=("--tenant-id" "${usage_tenant_id}")
fi

# Add status if provided
if [ -n "${usage_status:-}" ]; then
  args+=("--status" "${usage_status}")
fi

# Add all-statuses flag if provided
if [ "${usage_all_statuses:-false}" = "true" ]; then
  args+=("--all-statuses")
fi

# Add connector if provided (for backfill)
if [ -n "${usage_connector:-}" ]; then
  args+=("--connector" "${usage_connector}")
fi

# Add config-file if provided (for backfill)
if [ -n "${usage_config_file:-}" ]; then
  args+=("--config-file" "${usage_config_file}")
fi

# Add csv path if provided (for health)
if [ -n "${usage_csv:-}" ]; then
  args+=("--csv" "${usage_csv}")
fi

# Execute with all arguments passed through
exec uv run python -m connectors.cli "${subcommand}" "${args[@]}"
