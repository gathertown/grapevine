import { Request, Response, NextFunction } from 'express';
import { LogContext } from '../utils/logger.js';

/**
 * Middleware that adds user, organization, and tenant to the logger context
 * Must be placed after auth middleware
 */
export function userContextMiddleware(req: Request, _res: Response, next: NextFunction): void {
  if (req.user) {
    // Add user context to the existing logging context
    const userContext = {
      // underscores match how they're logged from python services
      user_id: req.user.id,
      organization_id: req.user.organizationId,
      tenant_id: req.user.tenantId,
    };
    LogContext.run(userContext, next);
  } else {
    next();
  }
}
