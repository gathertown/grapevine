# Backfill Config Examples

This directory contains example configuration files for connectors that require additional parameters beyond the tenant ID.

## Usage

When running the backfill CLI, you can provide a config file using the `--config-file` flag:

```bash
mise backfill -t <tenant-id> --config-file scripts/backfill_example_configs/slack.json
```

## Available Configs

### Slack (`slack.json`)

Required for Slack backfills. Provides the S3 URI where the Slack export ZIP file is located.

**Fields:**
- `s3_uri`: S3 URI pointing to the Slack export ZIP file

**Example:**
```json
{
  "s3_uri": "s3://my-bucket/my-tenant-id/slack-export.zip"
}
```

### Zendesk (`zendesk-window.json`)

Optional for Zendesk backfills. By default, Zendesk performs a full backfill. Use this config to specify a custom time window.

**Fields:**
- `start_timestamp`: ISO 8601 timestamp for the start of the window
- `end_timestamp`: ISO 8601 timestamp for the end of the window

**Example:**
```json
{
  "start_timestamp": "2024-01-01T00:00:00Z",
  "end_timestamp": "2024-12-31T23:59:59Z"
}
```

## Creating Custom Configs

1. Copy the example file for your connector
2. Update the values to match your requirements
3. Save it with a descriptive name
4. Pass it to the backfill CLI using `--config-file`
