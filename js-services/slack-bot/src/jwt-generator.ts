import jwt from 'jsonwebtoken';
import { config } from './config';
import { PermissionAudience } from './types';

interface JWTPayload {
  iss?: string; // issuer
  aud?: string; // audience
  sub?: string; // subject
  tenant_id: string; // tenant ID for multi-tenant access
  email?: string; // user email for permissions
  permission_audience?: PermissionAudience; // permission audience for document filtering
  nonBillable?: boolean; // if true, this request should NOT be counted as billable (default: false, meaning billable)
  exp?: number; // expiration time
  iat?: number; // issued at
}

/**
 * Generate an internal JWT token for MCP server authentication
 * @param tenantId - Tenant ID to include in the token
 * @param email - User email for permissions (optional)
 * @param expiresIn - Token expiration (default: 1 hour)
 * @param permissionAudience - Permission audience for document filtering
 * @param nonBillable - If true, this request should NOT be counted as billable (default: false, meaning billable)
 * @returns Signed JWT token
 */
export function generateInternalJWT(
  tenantId: string,
  email?: string,
  expiresIn: string = '1h',
  permissionAudience?: PermissionAudience,
  nonBillable: boolean = false
): string {
  const now = Math.floor(Date.now() / 1000);

  const payload: JWTPayload = {
    tenant_id: tenantId,
    iat: now,
  };

  // Only add nonBillable if true (omit if false for cleaner JWTs)
  if (nonBillable) {
    payload.nonBillable = true;
  }

  // Add email if provided
  if (email) {
    payload.email = email;
  }

  // Add permission audience if provided
  if (permissionAudience) {
    payload.permission_audience = permissionAudience;
  }

  // Add issuer if configured
  if (config.internalJwtIssuer) {
    payload.iss = config.internalJwtIssuer;
  }

  // Add audience if configured
  if (config.internalJwtAudience) {
    payload.aud = config.internalJwtAudience;
  }

  const options: jwt.SignOptions = {
    expiresIn,
  };

  // Use RSA private key for signing
  if (config.internalJwtPrivateKey) {
    return jwt.sign(payload, config.internalJwtPrivateKey, {
      ...options,
      algorithm: 'RS256',
    });
  } else {
    throw new Error('JWT signing configuration missing: INTERNAL_JWT_PRIVATE_KEY is required');
  }
}

/**
 * Verify and decode an internal JWT token (for testing purposes)
 * @param token - JWT token to verify
 * @returns Decoded payload
 */
export function verifyInternalJWT(token: string): JWTPayload {
  try {
    // Use RSA public key for verification
    if (config.internalJwtPublicKey) {
      return jwt.verify(token, config.internalJwtPublicKey, {
        algorithms: ['RS256'],
        issuer: config.internalJwtIssuer,
        audience: config.internalJwtAudience,
      }) as JWTPayload;
    } else {
      throw new Error(
        'JWT verification configuration missing: INTERNAL_JWT_PUBLIC_KEY is required'
      );
    }
  } catch (error) {
    throw new Error(
      `JWT verification failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
