#!/bin/bash

# Check if uv is installed and project dependencies are synced
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   Then run: uv sync --group test"
    exit 1
fi

# Check if the virtual environment exists and has ruff
if ! uv run ruff --version &> /dev/null; then
    echo "❌ Project dependencies not installed or ruff not available."
    echo "   Please run: uv sync --group test"
    exit 1
fi

# All checks passed, run the actual command
exec "$@"