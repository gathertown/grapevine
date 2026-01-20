/**
 * Auth Router
 * Verifies incoming JWTs from supported issuers (WorkOS/AuthKit).
 */

import type { AuthUser } from './types/auth.js';
import { getWorkOSJWKSHelper } from './workos-client.js';

/**
 * Determines the token type and routes to appropriate verification
 */
export async function verifyToken(token: string): Promise<AuthUser | null> {
  // WorkOS/AuthKit JWT verification
  return verifyWorkOSToken(token);
}

/**
 * Verify WorkOS JWT token
 */
async function verifyWorkOSToken(token: string): Promise<AuthUser | null> {
  const jwksHelper = getWorkOSJWKSHelper();
  if (!jwksHelper) {
    throw new Error('WorkOS JWT verification not configured - missing WORKOS_CLIENT_ID');
  }

  return jwksHelper.verifyAndExtractUser(token);
}
