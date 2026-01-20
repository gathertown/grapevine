#!/bin/bash

# Exit on error
set -e

echo "Running code quality checks..."
echo "=============================="

# 1. Auto-fix lint issues
echo "1. Auto-fixing lint issues..."
uv run ruff check --fix

# 2. Format code
echo "2. Formatting code..."
uv run ruff format

# 3. Verify lint passes
echo "3. Verifying lint passes..."
uv run ruff check

# 4. Check types
echo "4. Checking types..."
uv run mypy

# 5. Check for dead code
echo "5. Checking for dead code..."
uv run vulture

echo "6. Checking js-services..."
cd js-services
npm run lint
npm run type-check
cd ..

echo "=============================="
echo "✅ All checks passed!"