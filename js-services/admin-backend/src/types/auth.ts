import { Request } from 'express';
import { Pool } from 'pg';

export interface AuthUser {
  // WorkOS user ID.
  id: string;

  // Note: organizationId is required for WorkOS auth, but proper abstraction from WorkOS as a user
  // system means we should mostly use tenantId within application code.
  organizationId: string;

  email?: string;
  firstName?: string;
  lastName?: string;
  tenantId?: string;
  role?: string;
  permissions?: string[];
}

export interface AuthRequest extends Request {
  // Main user context for Grapevine with WorkOS-specific details.
  user?: AuthUser | null;

  // Database pool will be injected by middleware.
  db?: Pool;
}
