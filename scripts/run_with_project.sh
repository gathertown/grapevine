#!/usr/bin/env bash
# Runs the provided command with a given environment, passing through
# arguments and flags.
# 
# Note: Environment variables should be set in your shell or .env files
# before running this script.

set -euo pipefail

new_args=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --gv-env)
      # Legacy flag - now ignored
      if [[ $# -lt 2 ]]; then
        echo "Error: --gv-env requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --gv-env=*)
      # Legacy flag - now ignored
      shift
      ;;
    *)
      new_args+=("$1")
      shift
      ;;
  esac
done

exec "${new_args[@]}"
