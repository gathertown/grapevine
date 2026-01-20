/**
 * Authentication Middleware
 * Handles JWT token verification (WorkOS/AuthKit) and user context injection
 */

import type { Request, Response, NextFunction } from 'express';
import { verifyToken } from '../auth-router';
import { resolveWorkosOrgToTenant, createTenantProvisioningRequest } from '../control-db';
import { logger } from '../utils/logger';

/**
 * Middleware that extracts and verifies JWT token (WorkOS/AuthKit), injecting user context into the request.
 */
export async function injectUserContext(
  req: Request,
  _res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const authHeader = req.headers.authorization;

    if (authHeader && authHeader.startsWith('Bearer ')) {
      await handleWorkosJwtAuthentication(req, authHeader);
      next();
      return;
    }

    // No authentication found
    req.user = null;
    next();
  } catch (error) {
    logger.error('Authentication error', error);
    req.user = null;
    next();
  }
}

/**
 * Handles WorkOS/AuthKit JWT authentication
 */
async function handleWorkosJwtAuthentication(req: Request, authHeader: string): Promise<void> {
  const accessToken = authHeader.substring(7); // Remove 'Bearer ' prefix

  // Verify JWT token using appropriate handler (WorkOS or other)
  const user = await verifyToken(accessToken);

  if (!user) {
    req.user = null;
    return;
  }

  // Log user details for debugging role issues
  logger.info('WorkOS JWT user extracted', {
    userId: user.id,
    email: user.email,
    role: user.role,
    organizationId: user.organizationId,
    permissions: user.permissions,
  });

  // Resolve WorkOS org ID to tenant information if organization is present. Downstream of this,
  // we should prefer using tenantId in application code rather than organizationId; this allows
  // us to create an abstraction layer between WorkOS and our application.
  if (user.organizationId) {
    try {
      // Resolve WorkOS org ID to tenant information
      const tenantInfo = await resolveWorkosOrgToTenant(user.organizationId);
      if (!tenantInfo) {
        // No tenant exists at all - create provisioning request
        logger.info(
          `No tenant found for org ${user.organizationId}, creating provisioning request`,
          { organizationId: user.organizationId, userId: user.id }
        );
        await createTenantProvisioningRequest(user.organizationId);
      } else if (tenantInfo.isProvisioned) {
        // Tenant is provisioned and ready to use
        user.tenantId = tenantInfo.tenantId;
        logger.info(
          `Resolved org ${user.organizationId} to provisioned tenant ${tenantInfo.tenantId}`,
          {
            organizationId: user.organizationId,
            tenantId: tenantInfo.tenantId,
            userId: user.id,
          }
        );
      } else {
        // Tenant exists but is not yet provisioned (pending/provisioning/error)
        logger.info(
          `Tenant ${tenantInfo.tenantId} exists for org ${user.organizationId} but is not provisioned yet`,
          {
            organizationId: user.organizationId,
            tenantId: tenantInfo.tenantId,
            state: tenantInfo.state,
            userId: user.id,
          }
        );
        // Don't create another provisioning request, just continue without tenant ID
      }
    } catch (error) {
      logger.error(`Error resolving org ${user.organizationId} to tenant`, {
        organizationId: user.organizationId,
        userId: user.id,
        error: String(error),
      });
      // Re-throw database errors - don't silently ignore them
      throw error;
    }
  }

  req.user = user;
  logger.debug('JWT verification successful', {
    userId: user.id,
    organizationId: user.organizationId,
    tenantId: user.tenantId,
  });
}

/**
 * Middleware that requires an authenticated user. This should be used AFTER injectUserContext has
 * already run. It simply checks if req.user exists and returns 401 if not.
 */
export function requireUser(req: Request, res: Response, next: NextFunction): void {
  if (!req.user) {
    res.status(401).json({ error: 'Authentication required' });
    return;
  }
  next();
}

/**
 * Middleware that requires an admin user. Checks both authentication and admin role.
 */
export function requireAdmin(req: Request, res: Response, next: NextFunction): void {
  if (!req.user) {
    logger.warn('requireAdmin: No user found in request');
    res.status(401).json({ error: 'Authentication required' });
    return;
  }

  logger.info('requireAdmin: Checking user role', {
    userId: req.user.id,
    email: req.user.email,
    role: req.user.role,
    roleType: typeof req.user.role,
    organizationId: req.user.organizationId,
  });

  if (req.user.role !== 'admin') {
    logger.warn('requireAdmin: User does not have admin role', {
      userId: req.user.id,
      email: req.user.email,
      role: req.user.role,
      roleType: typeof req.user.role,
    });
    res.status(403).json({
      error: 'Admin access required',
      message:
        'You do not have permission to access this resource. Please contact your administrator.',
    });
    return;
  }

  logger.info('requireAdmin: Admin access granted', {
    userId: req.user.id,
    email: req.user.email,
  });

  next();
}
