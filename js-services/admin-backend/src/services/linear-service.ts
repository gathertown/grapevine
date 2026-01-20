/**
 * Linear Token Management Service - Admin Backend Instance
 *
 * Instantiates the LinearService from backend-common with admin-backend's config managers.
 */

import { LinearService } from '@corporate-context/backend-common';
import { ssmConfigManager } from '../config/ssm-config-manager.js';
import { dbConfigManager } from '../config/db-config-manager.js';

// Export singleton instance with admin-backend's config managers
export const linearService = new LinearService({
  ssmConfigManager,
  dbConfigManager,
});
