#!/bin/bash

# Change to js-services directory
cd js-services || exit 1

# Run yarn format and capture output
output=$(NX_TUI=false yarn format 2>&1)
exit_code=$?

if [ $exit_code -eq 0 ]; then
    # Check if any files were actually modified by using git diff
    # This is more reliable than parsing Prettier's output
    files_reformatted=$(git diff --name-only | grep -qE "\.(ts|tsx|js|jsx|json|md|yaml|yml)$" | wc -l)
    if [ $files_reformatted -gt 0 ]; then
        echo "✅ js-format: Files were reformatted, add them back and recommit"
        exit 1  # Exit with error code so pre-commit fails and user can re-add files
    else
        echo "✅ js-format: No formatting changes needed"
        exit 0
    fi
else
    # If yarn format failed, show the error
    echo "$output"
    exit $exit_code
fi
