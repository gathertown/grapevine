#!/bin/bash

# Run ruff check --fix and capture output
output=$(uv run ruff check --fix --unsafe-fixes "$@" 2>&1)
exit_code=$?

# If ruff made changes (exit code 1) or succeeded (exit code 0), show what was fixed
if [ $exit_code -eq 0 ] || [ $exit_code -eq 1 ]; then
    if echo "$output" | grep -qE "(Fixed|fixed)" || [ $exit_code -eq 1 ]; then
        echo "$output"
        echo "✅ ruff-fix: Files were automatically fixed (run 'git add' to stage changes)"
    else
        echo "✅ ruff-fix: No fixes needed"
    fi
    exit 0
else
    # Actual error occurred
    echo "$output"
    exit $exit_code
fi