#!/bin/bash

# Configuration
DB_HOST="localhost"
DB_PORT="5422"
DB_USER="postgres"
DB_PASSWORD="postgres"
DB_NAME="grapevine_control"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running database setup and migrations using migration CLI...${NC}"

# Function to run psql command
run_psql() {
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$1" -c "$2"
}

# Create grapevine_admin database - see: PG_TENANT_DATABASE_ADMIN_DB
echo -e "${YELLOW}Creating grapevine_admin database...${NC}"
if run_psql "postgres" "CREATE DATABASE grapevine_admin;" 2>/dev/null; then
    echo -e "${GREEN}✓ grapevine_admin database created successfully${NC}"
else
    echo -e "${YELLOW}⚠ grapevine_admin database may already exist${NC}"
fi

# Create grapevine_control database
echo -e "${YELLOW}Creating ${DB_NAME} database...${NC}"
if run_psql "postgres" "CREATE DATABASE ${DB_NAME};" 2>/dev/null; then
    echo -e "${GREEN}✓ ${DB_NAME} database created successfully${NC}"
else
    echo -e "${YELLOW}⚠ ${DB_NAME} database may already exist${NC}"
fi

# Set up environment variables for migration CLI
export CONTROL_DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

echo -e "${YELLOW}Running control database migrations using migration CLI...${NC}"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo -e "${RED}✗ uv not found. Please install uv first.${NC}"
    exit 1
fi

# Run migrations using the migration CLI
if mise migrations migrate --control; then
    echo -e "${GREEN}✓ All control database migrations completed successfully!${NC}"
else
    echo -e "${RED}✗ Migration CLI failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Database setup completed successfully!${NC}"
echo -e "${YELLOW}Note: Use 'mise migrations status --control' to check migration status${NC}"