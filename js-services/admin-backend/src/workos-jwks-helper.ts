/**
 * JWKS Helper for WorkOS JWT verification
 * Manages JWKS keys and provides JWT verification functionality
 */

import { jwtVerify, importJWK, JWTPayload as JoseJWTPayload, JWK } from 'jose';
import type { AuthUser } from './types/auth.js';
import { logger, LogContext } from './utils/logger.js';

interface JWKSOptions {
  refreshInterval?: number;
  maxAge?: number;
}

interface KeyData {
  key: unknown; // Will be a CryptoKey but we can't import it in Node.js context
  alg: string;
  kid: string;
}

export class WorkOSJWKSHelper {
  private jwksUrl: string;
  private keys: Map<string, KeyData>;
  private keysFetchedAt: number | null;
  private refreshInterval: number;
  private maxAge: number;

  constructor(clientId: string, options: JWKSOptions = {}) {
    if (!clientId) {
      throw new Error('Client ID is required for JWKS verification');
    }

    this.jwksUrl = `https://api.workos.com/sso/jwks/${clientId}`;
    this.keys = new Map(); // Cache for imported keys
    this.keysFetchedAt = null;
    this.refreshInterval = options.refreshInterval || 3600000; // 1 hour default
    this.maxAge = options.maxAge || 86400000; // 24 hours default

    logger.info(`JWKS Helper initialized for client: ${clientId}`, { clientId });
  }

  /**
   * Fetch JWKS from WorkOS
   */
  async fetchJWKS() {
    return LogContext.run({ operation: 'fetch-jwks' }, async () => {
      try {
        logger.info(`Fetching JWKS from: ${this.jwksUrl}`, { jwksUrl: this.jwksUrl });
        const response = await fetch(this.jwksUrl);

        if (!response.ok) {
          throw new Error(`Failed to fetch JWKS: ${response.status} ${response.statusText}`);
        }

        const jwks = (await response.json()) as { keys: unknown[] };
        logger.info(`Fetched ${jwks.keys?.length || 0} keys from JWKS`, {
          keyCount: jwks.keys?.length || 0,
        });

        return jwks;
      } catch (error) {
        logger.error('Error fetching JWKS', { error: String(error) });
        throw error;
      }
    });
  }

  /**
   * Import and cache JWK keys
   */
  async importKeys(jwks: { keys: unknown[] }): Promise<Map<string, KeyData>> {
    const importedKeys = new Map<string, KeyData>();

    for (const key of jwks.keys) {
      try {
        const typedKey = key as { alg: string; kid: string };
        const importedKey = await importJWK(key as JWK, typedKey.alg);
        importedKeys.set(typedKey.kid, {
          key: importedKey,
          alg: typedKey.alg,
          kid: typedKey.kid,
        });
      } catch (error) {
        const typedKey = key as { kid?: string };
        logger.warn(`Failed to import key ${typedKey.kid}`, {
          kid: typedKey.kid,
          error: String(error),
        });
      }
    }

    logger.info(`Imported ${importedKeys.size} keys to cache`, {
      importedCount: importedKeys.size,
    });
    return importedKeys;
  }

  /**
   * Get keys with automatic refresh if needed
   */
  async getKeys() {
    const now = Date.now();

    // Check if we need to fetch/refresh keys
    if (!this.keysFetchedAt || now - this.keysFetchedAt > this.refreshInterval) {
      try {
        const jwks = await this.fetchJWKS();
        this.keys = await this.importKeys(jwks);
        this.keysFetchedAt = now;
        logger.info('JWKS keys refreshed successfully');
      } catch (error) {
        logger.error('Failed to refresh JWKS keys', { error: String(error) });
        // If we have existing keys and they're not too old, continue with them
        if (this.keys.size > 0 && this.keysFetchedAt && now - this.keysFetchedAt < this.maxAge) {
          logger.info('Using cached keys due to refresh failure');
        } else {
          throw error;
        }
      }
    }

    return this.keys;
  }

  /**
   * Verify JWT token
   */
  async verifyJWT(token: string): Promise<JoseJWTPayload> {
    try {
      // Get the key ID from the JWT header
      const [headerB64] = token.split('.');
      if (!headerB64) {
        throw new Error('Invalid JWT token format');
      }
      const header = JSON.parse(Buffer.from(headerB64, 'base64url').toString());
      const keyId = header.kid;

      if (!keyId) {
        throw new Error('JWT header missing key ID (kid)');
      }

      // Get keys and find the matching key
      const keys = await this.getKeys();
      const keyData = keys.get(keyId);

      if (!keyData) {
        throw new Error(`No key found for kid: ${keyId}`);
      }

      // Verify the JWT
      const { payload } = await jwtVerify(token, keyData.key as Parameters<typeof jwtVerify>[1], {
        algorithms: [keyData.alg],
        issuer: 'https://api.workos.com',
      });
      return payload;
    } catch (error) {
      logger.error('JWT verification failed', { error: String(error) });
      throw error;
    }
  }

  /**
   * Extract user information from JWT payload
   */
  extractUserInfo(payload: JoseJWTPayload): AuthUser {
    return {
      id: (payload.sub as string) || '',
      email: payload.email as string,
      firstName: (payload.given_name as string) || (payload.first_name as string),
      lastName: (payload.family_name as string) || (payload.last_name as string),
      organizationId: (payload.org_id as string) || '',
      role: payload.role as string,
      permissions: (payload.permissions as string[]) || [],
    };
  }

  /**
   * Verify JWT and extract user info in one call
   */
  async verifyAndExtractUser(token: string): Promise<AuthUser> {
    return LogContext.run({ operation: 'verify-extract-user' }, async () => {
      try {
        const payload = await this.verifyJWT(token);
        const user = this.extractUserInfo(payload);

        logger.info('User extracted from JWT', {
          userId: user.id,
          email: user.email,
          organizationId: user.organizationId,
        });

        return user;
      } catch (error) {
        logger.error('Failed to verify JWT and extract user', { error: String(error) });
        throw error;
      }
    });
  }
}
