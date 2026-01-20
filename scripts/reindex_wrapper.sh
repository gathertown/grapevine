#!/usr/bin/env bash
# Wrapper script for reindex CLI

set -euo pipefail

# Set AWS_REGION default if not provided
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Validate required arguments
if [ -z "${usage_tenant_id:-}" ]; then
  echo "Error: --tenant-id is required"
  exit 1
fi

if [ -z "${usage_source:-}" ]; then
  echo "Error: --source is required"
  exit 1
fi

if [ -z "${usage_entity_id:-}" ]; then
  echo "Error: --entity-id is required (can specify multiple times)"
  exit 1
fi

# Build arguments for reindex_single_document.py
args=("--tenant-id" "${usage_tenant_id}" "--source" "${usage_source}")

# Add entity ID(s) - mise can pass multiple values separated by spaces
# We need to handle both single and multiple values
if [ -n "${usage_entity_id:-}" ]; then
  # Split by spaces to handle multiple --entity-id flags
  for entity_id in ${usage_entity_id}; do
    args+=("--entity-id" "${entity_id}")
  done
fi

# Add optional flags
if [ "${usage_no_force:-false}" = "true" ]; then
  args+=("--no-force")
fi

if [ "${usage_turbopuffer_only:-false}" = "true" ]; then
  args+=("--turbopuffer-only")
fi

if [ "${usage_dry_run:-false}" = "true" ]; then
  args+=("--dry-run")
fi

# Execute with all arguments passed through
exec uv run python -m scripts.reindex_single_document "${args[@]}"
