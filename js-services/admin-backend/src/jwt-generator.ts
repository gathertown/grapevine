import { SignJWT, importPKCS8 } from 'jose';
import { logger } from './utils/logger.js';

interface CustomJWTPayload {
  iss?: string; // issuer
  aud?: string; // audience
  sub?: string; // subject
  tenant_id: string; // tenant ID for multi-tenant access
  email?: string; // user email for permissions
  exp?: number; // expiration time
  iat?: number; // issued at
  [key: string]: unknown; // Index signature for compatibility with jose
}

/**
 * Get JWT configuration from environment variables
 */
function getJWTConfig() {
  return {
    privateKey: process.env.INTERNAL_JWT_PRIVATE_KEY,
    issuer: process.env.INTERNAL_JWT_ISSUER,
    audience: process.env.INTERNAL_JWT_AUDIENCE,
    expiry: process.env.INTERNAL_JWT_EXPIRY || '1h',
  };
}

/**
 * Convert expiry string (like '1h', '30m') to seconds
 */
function expiryToSeconds(expiry: string): number {
  const match = expiry.match(/^(\d+)([smhd])$/);
  if (!match) {
    throw new Error(`Invalid expiry format: ${expiry}`);
  }

  const value = parseInt(match[1] || '0', 10);
  const unit = match[2] || '';

  switch (unit) {
    case 's':
      return value;
    case 'm':
      return value * 60;
    case 'h':
      return value * 60 * 60;
    case 'd':
      return value * 24 * 60 * 60;
    default:
      throw new Error(`Invalid expiry unit: ${unit}`);
  }
}

/**
 * Generate an internal JWT token for MCP server authentication
 * @param tenantId - Tenant ID to include in the token
 * @param expiresIn - Token expiration (default: from config or '1h')
 * @param email - Optional user email for permissions
 * @returns Signed JWT token
 */
export async function generateInternalJWT(
  tenantId: string,
  expiresIn?: string,
  email?: string
): Promise<string> {
  const config = getJWTConfig();
  const expiry = expiresIn || config.expiry || '1h';

  if (!config.privateKey || typeof config.privateKey !== 'string') {
    throw new Error('JWT signing configuration missing: INTERNAL_JWT_PRIVATE_KEY is required');
  }

  try {
    const now = Math.floor(Date.now() / 1000);
    const exp = now + expiryToSeconds(expiry);

    const payload: CustomJWTPayload = {
      tenant_id: tenantId,
      iat: now,
      exp,
    };

    // Add email if provided
    if (email) {
      payload.email = email;
    }

    // Add issuer if configured
    if (config.issuer) {
      payload.iss = config.issuer;
    }

    // Add audience if configured
    if (config.audience) {
      payload.aud = config.audience;
    }

    // Import the RSA private key
    const privateKey = await importPKCS8(config.privateKey, 'RS256');

    // Create and sign the JWT
    let jwt = new SignJWT(payload)
      .setProtectedHeader({ alg: 'RS256' })
      .setIssuedAt(now)
      .setExpirationTime(exp);

    if (config.issuer) {
      jwt = jwt.setIssuer(config.issuer);
    }

    if (config.audience) {
      jwt = jwt.setAudience(config.audience);
    }

    const token = await jwt.sign(privateKey);

    logger.debug('Generated internal JWT', {
      tenantId,
      expiresIn: expiry,
      hasIssuer: !!config.issuer,
      hasAudience: !!config.audience,
      operation: 'jwt-generation',
    });

    return token;
  } catch (error) {
    logger.error(
      'Failed to generate internal JWT',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId,
        expiresIn: expiry,
        operation: 'jwt-generation',
      }
    );
    throw new Error(
      `JWT generation failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
