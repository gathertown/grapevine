#!/usr/bin/env bash
# Thin wrapper around docker buildx build to ensure we pass tool
# versions to the container.

set -euo pipefail

build_args=()

# Set <TOOL>_VERSION from mise output.
readarray -t tool_versions < <(mise current | tr ' ' '|')
for tool_version in "${tool_versions[@]}"; do
  tool=$(awk -F '|' '{ print $1 }' <<< "$tool_version")
  version=$(awk -F '|' '{ print $2 }' <<< "$tool_version")

  build_args+=("--build-arg" "${tool^^}_VERSION=$version")
done

exec docker buildx build "${build_args[@]}" "$@"