#!/bin/bash

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Usage function
usage() {
    echo "Usage: $0 [environment]"
    echo "  environment: local (default), staging, or production"
    exit 1
}

# Get environment argument or default to local
ENV="${1:-local}"

# Validate environment
case "$ENV" in
    local|staging|production)
        ;;
    *)
        print_error "Invalid environment: $ENV"
        print_error "Valid environments: local, staging, production"
        exit 1
        ;;
esac

print_info "Deploying Confluence Auth Proxy to $ENV environment"

# Check required tools
if ! command -v forge &> /dev/null; then
    print_error "Atlassian Forge CLI is not installed or not in PATH"
    exit 1
fi

# Set CONFLUENCE_APP_PAGE_TITLE, CONFLUENCE_GATEKEEPER_URL based on environment
case "$ENV" in
    production)
        CONFLUENCE_APP_PAGE_TITLE="Grapevine"
        CONFLUENCE_GATEKEEPER_URL="https://confluence.ingest.getgrapevine.ai"
        ;;
    staging)
        CONFLUENCE_APP_PAGE_TITLE="Grapevine [staging]"
        CONFLUENCE_GATEKEEPER_URL="https://confluence.ingest.stg.getgrapevine.ai"
        ;;
    local)
        CONFLUENCE_APP_PAGE_TITLE="Grapevine [local]"
        if [ -z "${GATEKEEPER_URL:-}" ]; then
            print_error "GATEKEEPER_URL environment variable is required for local deployment"
            print_error "Example: export GATEKEEPER_URL=https://your-ngrok-url.ngrok-free.app"
            exit 1
        fi
        CONFLUENCE_GATEKEEPER_URL="$GATEKEEPER_URL"
        ;;
esac

print_info "Using CONFLUENCE_APP_PAGE_TITLE: $CONFLUENCE_APP_PAGE_TITLE"
print_info "Using CONFLUENCE_GATEKEEPER_URL: $CONFLUENCE_GATEKEEPER_URL"

# Cleanup function - removes generated manifest.yml
cleanup() {
    if [ -f "manifest.yml" ]; then
        rm -f "manifest.yml"
        print_info "Cleaned up generated manifest.yml"
    fi
}

trap cleanup EXIT

print_info "Generating manifest.yml from template with substituted variables..."

# Export the environment-specific variables
export CONFLUENCE_APP_PAGE_TITLE
export CONFLUENCE_GATEKEEPER_URL

# Substitute all variables in template
if ! envsubst < manifest.template.yml > manifest.yml 2>/dev/null; then
    print_error "Failed to substitute variables in manifest template"
    exit 1
fi

print_info "Generated manifest.yml with substituted variables"

# Verify the generated manifest has no remaining variables
if grep -q '\$[A-Z_]*' "manifest.yml"; then
    print_error "Some variables were not substituted in the manifest:"
    grep '\$[A-Z_]*' "manifest.yml" || true
    exit 1
fi

print_success "All variables successfully substituted"

print_info "Deploying to $ENV environment using Forge CLI..."

# Deploy using forge
if forge deploy -e production; then
    print_success "Successfully deployed Confluence Auth Proxy to $ENV environment!"
else
    print_error "Forge deployment failed"
    exit 1
fi

print_success "Deployment completed successfully!"
