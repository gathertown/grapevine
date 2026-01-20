/**
 * WorkOS Client Initialization
 * Handles WorkOS SDK and JWKS helper setup
 */

import { WorkOS } from '@workos-inc/node';
import { logger } from './utils/logger.js';
import { WorkOSJWKSHelper } from './workos-jwks-helper.js';

// Initialize WorkOS
let workos: WorkOS | null = null;
let jwksHelper: WorkOSJWKSHelper | null = null;

if (process.env.WORKOS_API_KEY) {
  workos = new WorkOS(process.env.WORKOS_API_KEY);
  logger.info('WorkOS initialized successfully');
} else {
  logger.warn('⚠️ WORKOS_API_KEY not found - organization management will be disabled');
}

// Initialize JWKS Helper for JWT verification
if (process.env.WORKOS_CLIENT_ID) {
  try {
    jwksHelper = new WorkOSJWKSHelper(process.env.WORKOS_CLIENT_ID);
    logger.info('JWKS Helper initialized successfully');
  } catch (error) {
    logger.error('Failed to initialize JWKS Helper', { error: String(error) });
  }
} else {
  logger.warn('⚠️ WORKOS_CLIENT_ID not found - JWT verification will be disabled');
}

/**
 * Get the WorkOS client instance
 */
export function getWorkOSClient(): WorkOS | null {
  return workos;
}

/**
 * Get the JWKS helper instance
 */
export function getWorkOSJWKSHelper(): WorkOSJWKSHelper | null {
  return jwksHelper;
}
