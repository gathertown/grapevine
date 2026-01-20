/**
 * Tenant Database Connection Manager Singleton
 *
 * Provides a shared DbConnectionManager instance for the Slack bot to avoid
 * connection pool starvation when processing multiple messages.
 */

import { DbConnectionManager } from '@corporate-context/backend-common';

// Singleton instance to be reused across all database operations
export const tenantDbConnectionManager = new DbConnectionManager();
