# Database Migration System

This document describes the database migration system for Grapevine, which manages both control and tenant database schemas.

## Overview

The migration system handles two types of databases:
- **Control Database**: Manages tenant metadata and system configuration
- **Tenant Databases**: Individual databases for each provisioned tenant

## Architecture

### Migration Files Structure
```
migrations/
├── control/              # Control database migrations
│   ├── 20250808124500_create_tenants_control_table.sql
│   └── 20250812000000_add_workos_org_id_to_tenants.sql
├── tenant/               # Tenant database migrations
│   ├── 20250822000000_add_doc_references_columns.sql
│   ├── 20250825000000_add_bot_response_message_id.sql
│   └── schema.sql        # Base schema file
├── create-migration.sh   # Generate new migrations
├── migrate-local.sh      # Run migrations locally
├── migrate-production.sh # Run migrations in production
└── migration-status.sh   # Check migration status
```

### Migration Naming Convention
- Format: `YYYYMMDDHHMMSS_description.sql`
- Example: `20250828120000_add_user_preferences_table.sql`
- The timestamp ensures proper ordering and uniqueness

## Python CLI Tool

The migration system uses a single Python CLI tool that provides all migration functionality.

### Commands

#### 1. Create Migration

Generate new migration files with proper naming and templates.

```bash
# Create control database migration
mise migrations create control "add workos org id column"

# Create tenant database migration  
mise migrations create tenant "create user preferences table"
```

#### 2. Run Migrations

Execute migrations with flexible targeting options.

```bash
# Migrate both control and all tenant databases
mise migrations migrate --control --all-tenants

# Migrate control database only
mise migrations migrate --control

# Migrate all tenant databases only
mise migrations migrate --all-tenants

# Migrate specific tenant
mise migrations migrate --tenant abc123def456

# Dry run (show what would be done)
mise migrations migrate --control --all-tenants --dry-run

# Production settings (higher retries, longer timeout)
mise migrations migrate --control --all-tenants --retries 5 --timeout 600 --max-parallel 3
```

**Migration Options:**
- `--control`: Migrate control database
- `--all-tenants`: Migrate all tenant databases  
- `--tenant <id>`: Migrate specific tenant database
- `--dry-run`: Show what would be done without executing
- `--retries <n>`: Number of retry attempts (default: 3)
- `--timeout <seconds>`: Migration timeout (default: 300)
- `--max-parallel <n>`: Max parallel tenant migrations (default: 5)

#### 3. Check Status

View migration status across databases.

```bash
# Check status of all databases
mise migrations status

# Verbose output (show all migrations with timestamps)
mise migrations status --verbose

# Control database only
mise migrations status --control

# All tenant databases
mise migrations status --all-tenants

# Specific tenant
mise migrations status --tenant abc123def456
```

#### 4. List Migrations

Show available migration files.

```bash
# List all migration files
mise migrations list

# Control migrations only
mise migrations list --control

# Tenant migrations only
mise migrations list --tenant
```

#### 5. Mark Migrations

Manually mark or unmark migrations as applied (for maintenance scenarios).

```bash
# Mark a migration as applied to control database
mise migrations mark --apply 20250828000000 --control

# Unmark a migration from specific tenant (allows re-run)
mise migrations mark --unapply 20250828000000 --tenant abc123

# Mark migration as applied to all tenants
mise migrations mark --apply 20250828000000 --all-tenants

# Dry run to see what would happen
mise migrations mark --apply 20250828000000 --control --dry-run

# Force operation (skip validation checks)
mise migrations mark --apply 20250828000000 --control --force

# DANGEROUS: Mark ALL migrations as applied (without running them)
mise migrations mark --DANGEROUS-apply-all --control --dry-run
mise migrations mark --DANGEROUS-apply-all --all-tenants
```

**Mark Command Options:**
- `--apply <version>`: Mark migration as applied
- `--unapply <version>`: Unmark migration (remove from applied)
- `--DANGEROUS-apply-all`: Mark ALL migrations as applied (use with extreme caution!)
- `--control`: Target control database
- `--all-tenants`: Target all tenant databases  
- `--tenant <id>`: Target specific tenant database
- `--dry-run`: Show what would be done without executing
- `--force`: Skip validation checks and force operation

**Use Cases for Mark Command:**
- Skip problematic migrations by marking them as applied
- Re-run migrations by unmarking them first
- Fix migration state inconsistencies
- Handle manual schema changes that bypass the migration system
- Import existing databases: Use `--DANGEROUS-apply-all` to mark all migrations as applied when importing databases that already have the schema

#### 6. Reset Databases

Reset (drop all data from) databases for local development. **Only works in local environments.**

```bash
# Reset control database
mise migrations reset --control

# Reset all tenant databases
mise migrations reset --all-tenants

# Reset specific tenant database
mise migrations reset --tenant abc123def456

# Reset both control and all tenant databases
mise migrations reset --control --all-tenants

# Dry run to see what would be reset
mise migrations reset --control --all-tenants --dry-run

# Skip confirmation prompts (DANGEROUS!)
mise migrations reset --control --force
```

**Reset Command Options:**
- `--control`: Reset control database
- `--all-tenants`: Reset all tenant databases
- `--tenant <id>`: Reset specific tenant database
- `--dry-run`: Show what would be done without executing
- `--force`: Skip confirmation prompts (DANGEROUS!)

**Use Cases for Reset Command:**
- Clean slate for local development testing
- Remove all test data between development sessions
- Reset databases to initial state for debugging
- Clear corrupted data during development

⚠️ **WARNING**: This command permanently deletes all data. Use with extreme caution and only in local development environments.

### Environment Variables

**Required:**
- `CONTROL_DATABASE_URL` - Control database connection string

**Optional (for tenant operations):**
- `PG_TENANT_DATABASE_HOST` - Tenant database host
- `PG_TENANT_DATABASE_PORT` - Tenant database port (default: 5432)
- `PG_TENANT_DATABASE_ADMIN_USERNAME` - Tenant database admin user
- `PG_TENANT_DATABASE_ADMIN_PASSWORD` - Tenant database admin password

## Local Development Workflow

This is the recommended workflow for local development and self-hosted deployments.

### 1. Initial Setup

After cloning the repository, run migrations to set up your database schema:

```bash
# Start your local databases (PostgreSQL must be running)
# Then run all migrations
mise migrations migrate --control --all-tenants

# Check that migrations were applied
mise migrations status
```

### 2. Creating a New Migration

```bash
# Generate migration file
mise migrations create tenant "add user preferences"

# Edit the generated file
# migrations/tenant/20250828120000_add_user_preferences.sql

# Apply locally
mise migrations migrate --control --all-tenants

# Check status
mise migrations status
```

### 3. Testing Migrations

Before committing, always test your migration:

```bash
# Check current status
mise migrations status --verbose

# Dry run to see what will be applied
mise migrations migrate --control --all-tenants --dry-run

# Apply the migration
mise migrations migrate --control --all-tenants

# Verify it was applied
mise migrations status
```

### 4. Resetting for Fresh Start

If you need to start fresh during development:

```bash
# Reset all databases (local only)
mise migrations reset --control --all-tenants

# Re-run all migrations
mise migrations migrate --control --all-tenants
```

### 5. Environment Setup

Create a `.env` file in the project root:

```env
# Control database
CONTROL_DATABASE_URL=postgresql://user:pass@localhost:5432/control_db

# Tenant database credentials (optional for local multi-tenant testing)
PG_TENANT_DATABASE_HOST=localhost
PG_TENANT_DATABASE_PORT=5432
PG_TENANT_DATABASE_ADMIN_USERNAME=admin
PG_TENANT_DATABASE_ADMIN_PASSWORD=password
```

## CI/CD Integration (Optional)

If you set up automated deployments, you can run migrations as part of your pipeline. Here's an example GitHub Actions workflow:

```yaml
# .github/workflows/deploy.yaml
migrate:
  runs-on: ubuntu-latest
  needs: build
  steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Run database migrations
      env:
        CONTROL_DATABASE_URL: ${{ secrets.CONTROL_DATABASE_URL }}
        PG_TENANT_DATABASE_HOST: ${{ secrets.PG_TENANT_DATABASE_HOST }}
        PG_TENANT_DATABASE_ADMIN_USERNAME: ${{ secrets.PG_TENANT_DATABASE_ADMIN_USERNAME }}
        PG_TENANT_DATABASE_ADMIN_PASSWORD: ${{ secrets.PG_TENANT_DATABASE_ADMIN_PASSWORD }}
      run: mise migrations migrate --control --all-tenants --retries 5 --timeout 600 --max-parallel 3
```

**Best Practice**: Run migrations before deploying new service versions to ensure the database schema is up-to-date.

## Migration Best Practices

### 1. Transaction Safety
Always wrap migrations in transactions:
```sql
BEGIN;

-- Your migration code here
CREATE TABLE example (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
```

### 2. Backward Compatibility
- Add columns instead of modifying existing ones
- Use nullable columns or provide defaults
- Create new tables/indexes before dropping old ones

### 3. Performance Considerations
```sql
-- Add indexes for large tables
CREATE INDEX CONCURRENTLY idx_documents_source ON documents(source);

-- Use appropriate data types
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,           -- Use BIGSERIAL for high-volume tables
    tenant_id UUID NOT NULL,           -- Use UUID for distributed systems
    created_at TIMESTAMPTZ DEFAULT NOW() -- Always use TIMESTAMPTZ
);
```

### 4. Data Migration
For complex data migrations, consider:
```sql
-- Example: Migrate data in batches
DO $$
DECLARE
    batch_size INTEGER := 1000;
    processed INTEGER := 0;
BEGIN
    LOOP
        UPDATE documents 
        SET new_column = old_column 
        WHERE id IN (
            SELECT id FROM documents 
            WHERE new_column IS NULL 
            LIMIT batch_size
        );
        
        GET DIAGNOSTICS processed = ROW_COUNT;
        EXIT WHEN processed = 0;
        
        RAISE NOTICE 'Processed % rows', processed;
    END LOOP;
END $$;
```

## Troubleshooting

### Common Issues

1. **Migration fails with timeout**
   - Increase timeout with `--timeout` flag
   - Break large migrations into smaller chunks

2. **Permission errors**
   - Ensure database user has necessary privileges
   - Check connection strings and credentials

3. **Migration already applied**
   - Check `schema_migrations` table
   - Use `--dry-run` to see what would be applied

4. **Tenant database not found**
   - Verify tenant is in 'provisioned' state
   - Check tenant database naming convention (`db_<tenant_id>`)

### Debugging Commands

```bash
# Check current migration status
mise migrations status --verbose

# Test database connectivity (CLI handles this automatically)
mise migrations status --control

# List all provisioned tenants (shown in status)
mise migrations status --all-tenants

# Check what migrations would run
mise migrations migrate --control --all-tenants --dry-run

# Mark a migration as applied without running it
mise migrations mark --apply 20250828000000 --control --dry-run
```

## Production Considerations

### 1. Zero-Downtime Migrations
- Use `ALTER TABLE ... ADD COLUMN` for new columns
- Use `CREATE INDEX CONCURRENTLY` for indexes
- Avoid `ALTER TABLE ... ALTER COLUMN` on large tables

### 2. Rollback Strategy
- Migrations are forward-only (no automatic rollback)
- For critical changes, prepare rollback migrations manually
- Test migrations thoroughly in a staging environment first

### 3. Monitoring
- Check migration status before and after deployment
- Log migration output for debugging
- Consider alerting on migration failures in production

### 4. Security
- Store database credentials securely (environment variables, secrets manager)
- Use SSL for database connections in production
- Limit migration user permissions to only what's needed

## Advanced Usage

### Custom Migration Validation
Add custom validation to migration files:

```sql
-- Validate data integrity
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM users WHERE email IS NULL) > 0 THEN
        RAISE EXCEPTION 'Cannot proceed: users with null email found';
    END IF;
END $$;
```

### Environment-Specific Migrations
Use conditional logic for different environments:

```sql
-- Only in production
DO $$
BEGIN
    IF current_setting('server_version_num')::int >= 140000 THEN
        -- PostgreSQL 14+ specific features
        ALTER TABLE documents ADD COLUMN vector_data vector(1536);
    END IF;
END $$;
```

This migration system provides a robust, scalable solution for managing database schema changes across both control and tenant databases while maintaining data integrity and deployment safety.
