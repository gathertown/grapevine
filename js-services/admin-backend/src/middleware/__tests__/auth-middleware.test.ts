/**
 * Tests for Authentication Middleware Route Guards
 */

import { Request, Response } from 'express';
import { requireUser, requireAdmin } from '../auth-middleware';
import type { AuthUser } from '../../types/auth';

describe('Authentication Middleware Route Guards', () => {
  let req: Partial<Request>;
  let res: Partial<Response>;
  let next: jest.Mock;

  beforeEach(() => {
    req = {};
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    next = jest.fn();
  });

  describe('requireUser', () => {
    it('should call next() when req.user exists', () => {
      req.user = {
        id: 'user1',
        email: 'test@example.com',
        organizationId: 'org_123',
      } satisfies AuthUser;

      requireUser(req as Request, res as Response, next);

      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should return 401 when req.user is null', () => {
      req.user = null;

      requireUser(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 401 when req.user is undefined', () => {
      req.user = undefined;

      requireUser(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(next).not.toHaveBeenCalled();
    });
  });

  describe('requireAdmin', () => {
    it('should call next() when req.user exists with admin role', () => {
      req.user = {
        id: 'user1',
        email: 'admin@example.com',
        organizationId: 'org_123',
        role: 'admin',
      } satisfies AuthUser;

      requireAdmin(req as Request, res as Response, next);

      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
      expect(res.json).not.toHaveBeenCalled();
    });

    it('should return 401 when req.user is null', () => {
      req.user = null;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 401 when req.user is undefined', () => {
      req.user = undefined;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 403 when req.user has member role', () => {
      req.user = {
        id: 'user1',
        email: 'member@example.com',
        organizationId: 'org_123',
        role: 'member',
      } satisfies AuthUser;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Admin access required',
        message:
          'You do not have permission to access this resource. Please contact your administrator.',
      });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 403 when req.user has no role', () => {
      req.user = {
        id: 'user1',
        email: 'user@example.com',
        organizationId: 'org_123',
        role: undefined,
      } satisfies AuthUser;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Admin access required',
        message:
          'You do not have permission to access this resource. Please contact your administrator.',
      });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 403 when req.user has empty string role', () => {
      req.user = {
        id: 'user1',
        email: 'user@example.com',
        organizationId: 'org_123',
        role: '',
      } satisfies AuthUser;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Admin access required',
        message:
          'You do not have permission to access this resource. Please contact your administrator.',
      });
      expect(next).not.toHaveBeenCalled();
    });

    it('should return 403 when req.user has unknown role', () => {
      req.user = {
        id: 'user1',
        email: 'user@example.com',
        organizationId: 'org_123',
        role: 'guest',
      } satisfies AuthUser;

      requireAdmin(req as Request, res as Response, next);

      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: 'Admin access required',
        message:
          'You do not have permission to access this resource. Please contact your administrator.',
      });
      expect(next).not.toHaveBeenCalled();
    });
  });
});
