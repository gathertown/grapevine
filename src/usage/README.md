# Usage Reporting CLI

A CLI tool for generating usage reports across all tenants based on Redis usage tracking data.

## Overview

The usage reporting CLI connects to Redis and aggregates usage data from time-series keys. It provides various output formats and filtering options to help analyze usage patterns across your Corporate Context deployment. The tool now uses Redis instead of tenant databases for improved performance and simplified architecture.

## Prerequisites

- CONTROL_DATABASE_URL environment variable (for tenant discovery)
- REDIS_PRIMARY_ENDPOINT environment variable (Redis connection, defaults to localhost:6379)

The tool connects to Redis directly to read usage data and to the control database to discover provisioned tenants. No complex credential management is needed since Redis usage keys follow a simple pattern.

## Commands

### Generate Full Report

```bash
# Generate a comprehensive usage report for all tenants
uv run python -m src.usage.cli report

# Generate report with date filters
uv run python -m src.usage.cli report --since 2025-09-01 --until 2025-09-12

# Generate report for specific tenant only
uv run python -m src.usage.cli report --tenant abc123

# Output to JSON file
uv run python -m src.usage.cli report --output usage_report.json --format json

# Output to CSV file 
uv run python -m src.usage.cli report --output usage_report.csv --format csv
```

### Quick Summary

```bash
# Show usage summary for last 30 days (default)
uv run python -m src.usage.cli summary

# Show usage summary for last 7 days
uv run python -m src.usage.cli summary --days 7

# Show summary for specific tenant
uv run python -m src.usage.cli summary --tenant abc123 --days 14
```

## Output Formats

### Table Format (Default)
- Rich formatted table with usage statistics
- Includes totals row and summary statistics
- Color-coded columns for easy reading
- Shows time ranges for each tenant

### JSON Format
- Structured JSON output with complete usage data
- Includes metadata like generation timestamp
- Suitable for programmatic processing
- Contains both summary and detailed breakdowns

### CSV Format  
- Simple CSV format for spreadsheet import
- Contains core metrics for each tenant
- Includes time range information
- Easy to process with other tools

## Usage Metrics Tracked

- **Requests**: Total number of API requests (ask_agent calls)
- **Input Tokens**: Tokens consumed in user inputs
- **Output Tokens**: Tokens generated in responses  
- **Embedding Tokens**: Tokens used for document embedding
- **Total Tokens**: Sum of all token types

## Redis Key Structure

Usage data is stored in Redis using time-series keys:

```
usage:{tenant_id}:{metric_type}:{YYYY-MM}
```

**Examples**:
- `usage:abc123:requests:2025-01` - January 2025 request count for tenant abc123
- `usage:def456:input_tokens:2025-01` - January 2025 input token count for tenant def456

The CLI tool queries these keys across date ranges to generate reports.

## Performance Options

- `--max-parallel`: Control concurrent Redis queries (default: 10)
- Automatic connection testing and error handling
- Graceful handling of missing Redis keys or connection issues

## Example Output

```
Usage Report Summary (Redis Data)
┌─────────────────┬──────────┬─────────────┬──────────────┬──────────────────┬─────────────┬────────────────────┐
│ Tenant ID       │ Requests │ Input Tokens │ Output Tokens │ Embedding Tokens │ Total Tokens │ Month Range        │
├─────────────────┼──────────┼─────────────┼──────────────┼──────────────────┼─────────────┼────────────────────┤
│ abc123def456    │ 1,250    │ 45,000      │ 62,000       │ 125,000          │ 232,000     │ 2025-08 to         │
│                 │          │             │              │                  │             │ 2025-09            │
│ xyz789abc123    │ 890      │ 32,000      │ 44,000       │ 89,000           │ 165,000     │ 2025-09            │
├─────────────────┼──────────┼─────────────┼──────────────┼──────────────────┼─────────────┼────────────────────┤
│ TOTAL           │ 2,140    │ 77,000      │ 106,000      │ 214,000          │ 397,000     │ 2 tenants          │
└─────────────────┴──────────┴─────────────┴──────────────┴──────────────────┴─────────────┴────────────────────┘

Statistics:
• Tenants with usage: 2
• Average requests per tenant: 1,070
• Average tokens per tenant: 198,500
• Top usage tenant: abc123def456 (232,000 tokens)
```

## Integration

This CLI follows the same patterns as the migrations CLI (`src.migrations.cli`) and can be used in similar contexts:

- CI/CD pipelines for usage monitoring
- Billing system integration
- Operational monitoring and alerting
- Customer usage analysis

## Error Handling

- **Redis connectivity issues**: Graceful failure with clear error messages
- **Missing keys**: Handles tenants without usage data (reports zero usage)
- **Connection timeouts**: Robust retry logic and timeout handling
- **Environment validation**: Checks required environment variables upfront