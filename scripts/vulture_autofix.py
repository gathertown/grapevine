#!/usr/bin/env python
"""
Autofix script for vulture high-confidence dead code detection.
Processes vulture output and automatically removes 100% confidence dead code.
"""

import re
import subprocess
import sys
from pathlib import Path


def run_vulture_100_percent() -> str:
    """Run vulture with 100% confidence to get guaranteed dead code."""
    try:
        result = subprocess.run(
            ["uv", "run", "vulture", "--min-confidence", "100"],
            capture_output=True,
            text=True,
            check=False,
        )
        # Vulture outputs to stderr, not stdout
        return result.stderr if result.stderr else result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running vulture: {e}")
        return ""


def parse_vulture_output(output: str) -> list[dict[str, str | int]]:
    """
    Parse vulture output to extract file paths, line numbers, and issue types.

    Expected format:
    src/example.py:123: unused function 'foo' (100% confidence)
    src/example.py:456: unreachable code (100% confidence)
    """
    issues = []
    lines = output.strip().split("\n")

    for line in lines:
        if not line.strip():
            continue

        # Match: file:line: issue type 'name' (confidence%)
        # or: file:line: issue type (confidence%)
        match = re.match(
            r"^(.+):(\d+):\s+(.*?)\s+\((\d+)%\s+confidence(?:,\s+\d+\s+line)?.*?\)$", line.strip()
        )

        if match:
            file_path, line_num, description, confidence = match.groups()

            if int(confidence) >= 100:  # Only process 100% confidence
                issues.append(
                    {
                        "file": file_path,
                        "line": int(line_num),
                        "description": description,
                        "confidence": int(confidence),
                    }
                )

    return issues


def remove_dead_code_lines(file_path: str, lines_to_remove: list[int]) -> bool:
    """
    Remove specific lines from a file.
    Returns True if file was modified, False otherwise.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            print(f"Warning: File {file_path} does not exist")
            return False

        with open(path, encoding="utf-8") as f:
            file_lines = f.readlines()

        # Sort in reverse order to avoid index shifting
        lines_to_remove_sorted = sorted(set(lines_to_remove), reverse=True)

        original_length = len(file_lines)

        for line_num in lines_to_remove_sorted:
            # Convert to 0-based index
            index = line_num - 1
            if 0 <= index < len(file_lines):
                # Check if it's just whitespace or a simple statement
                line_content = file_lines[index].strip()

                # Only remove if it's a simple/safe removal
                if (
                    line_content == ""
                    or line_content.startswith("#")
                    or re.match(r"^\s*(pass|return|continue|break)\s*$", line_content)
                    or re.match(r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=.*$", line_content)
                ):
                    del file_lines[index]

        # Only write if we actually removed something
        if len(file_lines) < original_length:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(file_lines)

            removed_count = original_length - len(file_lines)
            print(f"Removed {removed_count} lines from {file_path}")
            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def group_issues_by_file(issues: list[dict[str, str | int]]) -> dict[str, list[int]]:
    """Group issues by file path and collect line numbers."""
    file_issues: dict[str, list[int]] = {}

    for issue in issues:
        file_path = str(issue["file"])
        line_num = int(issue["line"])

        if file_path not in file_issues:
            file_issues[file_path] = []

        file_issues[file_path].append(line_num)

    return file_issues


def main():
    """Main function to run vulture autofix."""
    print("🔍 Running vulture autofix for 100% confidence dead code...")

    # Get vulture output
    vulture_output = run_vulture_100_percent()

    if not vulture_output.strip():
        print("✅ No 100% confidence dead code found!")
        return 0

    print(f"📝 Vulture output:\n{vulture_output}")

    # Parse issues
    issues = parse_vulture_output(vulture_output)

    if not issues:
        print("ℹ️  No parseable 100% confidence issues found")
        return 0

    print(f"🎯 Found {len(issues)} high-confidence issues to fix")

    # Group by file
    file_issues = group_issues_by_file(issues)

    modified_files = []

    # Process each file
    for file_path, line_numbers in file_issues.items():
        print(f"\n🔧 Processing {file_path} (lines: {line_numbers})")

        if remove_dead_code_lines(file_path, line_numbers):
            modified_files.append(file_path)

    if modified_files:
        print(f"\n✅ Successfully modified {len(modified_files)} files:")
        for file_path in modified_files:
            print(f"   - {file_path}")
    else:
        print("\n⚠️  No files were modified (issues may be too complex for autofix)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
