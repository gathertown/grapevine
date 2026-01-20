# Database Migrations

This directory contains all database migration files for Corporate Context.

## Directory Structure

```
migrations/
├── control/                  # Control database migration files
│   ├── 20250808124500_create_tenants_control_table.sql
│   └── 20250812000000_add_workos_org_id_to_tenants.sql
├── tenant/                   # Tenant database migration files
│   ├── 20250822000000_add_doc_references_columns.sql
│   ├── schema.sql
│   └── ...
└── README.md                 # This file
```

## Quick Start

```bash
# Create a new migration
mise migrations create tenant "add user preferences table"

# Run migrations locally
mise migrations migrate --control --all-tenants

# Check migration status
mise migrations status

# List existing migrations
mise migrations list

# Mark/unmark migrations (for manual maintenance)
mise migrations mark --apply 20250828000000 --control
mise migrations mark --unapply 20250828000000 --tenant abc123
mise migrations mark --DANGEROUS-apply-all --all-tenants --dry-run
```

## CLI Commands

The migration system uses a single Python CLI tool:

```bash
# Migration creation
mise migrations create control "add workos org id column"
mise migrations create tenant "create user preferences table"

# Migration execution
mise migrations migrate --control --all-tenants
mise migrations migrate --tenant abc123def456
mise migrations migrate --control --all-tenants --dry-run

# Status checking
mise migrations status --verbose
mise migrations status --control
mise migrations status --all-tenants

# List migrations
mise migrations list --control
mise migrations list --tenant

# Manual migration marking (for maintenance)
mise migrations mark --apply 20250828000000 --control
mise migrations mark --unapply 20250828000000 --tenant abc123
mise migrations mark --apply 20250828000000 --all-tenants --dry-run
mise migrations mark --DANGEROUS-apply-all --control
```

## Targetting an Environment

To target an environment, pass the `--gv-env` flag to `mise migrations`.
For example: `mise migrations --gv-env local status`.

By default `local` is targeted,

## Migration Files

Migration files are stored in this directory:
- `control/` - Control database migrations
- `tenant/` - Tenant database migrations

For complete documentation, see [docs/migrations.md](../docs/migrations.md).
