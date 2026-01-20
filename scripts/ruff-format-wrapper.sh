#!/bin/bash

# Run ruff format and capture which files were reformatted
output=$(uv run ruff format "$@" 2>&1)
exit_code=$?

if [ $exit_code -eq 0 ]; then
    # Count how many files were actually reformatted
    reformatted_count=$(echo "$output" | grep -c "reformatted" || echo "0")
    
    if [ "$reformatted_count" -gt 0 ]; then
        echo "$output"
        echo "✅ ruff-format: $reformatted_count files were reformatted (run 'git add' to stage changes)"
    else
        echo "✅ ruff-format: No formatting changes needed"
    fi
    exit 0
else
    echo "$output"
    exit $exit_code
fi
