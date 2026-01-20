/**
 * Linear Service for Slack Bot
 *
 * Provides Linear token management with automatic refresh for the Slack bot.
 * Uses shared createLinearService factory from backend-common.
 */

import { TenantConfigManager, createLinearService } from '@corporate-context/backend-common';
import { tenantDbConnectionManager } from '../config/tenantDbConnectionManager';

// Create base tenant config manager for Linear service
const baseTenantConfigManager = new TenantConfigManager({
  getDbPool: (tenantId: string) => tenantDbConnectionManager.get(tenantId),
});

// Export singleton LinearService instance
export const linearService = createLinearService(baseTenantConfigManager);
