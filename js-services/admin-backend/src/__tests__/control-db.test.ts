/**
 * Tests for control-db functions
 */

// Mock the logger first
jest.mock('../utils/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
  LogContext: {
    run: jest.fn((_context, fn) => fn()),
  },
}));

// Create the mock pool and query function
const mockQuery = jest.fn();
const mockEnd = jest.fn();
const mockPool = {
  query: mockQuery,
  end: mockEnd,
};

// Mock pg module
jest.mock('pg', () => ({
  Pool: jest.fn(() => mockPool),
}));

// Now we can import the module - it will use our mocked Pool
import {
  resolveTenantToWorkosOrg,
  getTenantInfoById,
  resolveWorkosOrgToTenant,
  closeControlDbPool,
} from '../control-db';

describe('Control DB Functions', () => {
  beforeEach(async () => {
    // Reset all mocks
    jest.clearAllMocks();

    // Set environment variable for each test
    process.env.CONTROL_DATABASE_URL = 'postgresql://test@localhost/test';

    // Close any existing pool to force recreation
    await closeControlDbPool();
  });

  afterEach(async () => {
    delete process.env.CONTROL_DATABASE_URL;
    await closeControlDbPool();
  });

  describe('resolveTenantToWorkosOrg', () => {
    it('should return WorkOS org ID when tenant exists', async () => {
      const tenantId = 'tenant123';
      const workosOrgId = 'org_123456789';

      mockQuery.mockResolvedValueOnce({
        rows: [{ workos_org_id: workosOrgId }],
      });

      const result = await resolveTenantToWorkosOrg(tenantId);

      expect(result).toBe(workosOrgId);
      expect(mockQuery).toHaveBeenCalledWith(
        `SELECT workos_org_id FROM public.tenants
       WHERE id = $1`,
        [tenantId]
      );
    });

    it('should return null when tenant does not exist', async () => {
      const tenantId = 'nonexistent';

      mockQuery.mockResolvedValueOnce({
        rows: [],
      });

      const result = await resolveTenantToWorkosOrg(tenantId);

      expect(result).toBeNull();
      expect(mockQuery).toHaveBeenCalledWith(
        `SELECT workos_org_id FROM public.tenants
       WHERE id = $1`,
        [tenantId]
      );
    });

    it('should throw error when control database is not available', async () => {
      // Remove environment variable to simulate no database
      delete process.env.CONTROL_DATABASE_URL;

      await expect(resolveTenantToWorkosOrg('tenant123')).rejects.toThrow(
        'Control database not available for tenant-to-org resolution'
      );
    });

    it('should propagate database errors', async () => {
      const tenantId = 'tenant123';
      const dbError = new Error('Database connection failed');

      mockQuery.mockRejectedValueOnce(dbError);

      await expect(resolveTenantToWorkosOrg(tenantId)).rejects.toThrow(dbError);
    });
  });

  describe('getTenantInfoById', () => {
    it('should return tenant info when tenant exists', async () => {
      const tenantId = 'tenant123';
      const state = 'provisioned';
      const errorMessage = null;

      mockQuery.mockResolvedValueOnce({
        rows: [{ id: tenantId, state, error_message: errorMessage }],
      });

      const result = await getTenantInfoById(tenantId);

      expect(result).toEqual({
        tenantId,
        isProvisioned: true,
        state,
        errorMessage,
      });
    });

    it('should return tenant info with error state', async () => {
      const tenantId = 'tenant123';
      const state = 'error';
      const errorMessage = 'Provisioning failed';

      mockQuery.mockResolvedValueOnce({
        rows: [{ id: tenantId, state, error_message: errorMessage }],
      });

      const result = await getTenantInfoById(tenantId);

      expect(result).toEqual({
        tenantId,
        isProvisioned: false,
        state,
        errorMessage,
      });
    });

    it('should return null when tenant does not exist', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [],
      });

      const result = await getTenantInfoById('nonexistent');

      expect(result).toBeNull();
    });
  });

  describe('resolveWorkosOrgToTenant', () => {
    it('should return tenant info when WorkOS org exists', async () => {
      const workosOrgId = 'org_123456789';
      const tenantId = 'tenant123';
      const state = 'provisioned';
      const errorMessage = null;

      mockQuery.mockResolvedValueOnce({
        rows: [{ id: tenantId, state, error_message: errorMessage }],
      });

      const result = await resolveWorkosOrgToTenant(workosOrgId);

      expect(result).toEqual({
        tenantId,
        isProvisioned: true,
        state,
        errorMessage,
      });
    });

    it('should return null when WorkOS org does not exist', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [],
      });

      const result = await resolveWorkosOrgToTenant('nonexistent');

      expect(result).toBeNull();
    });

    it('should handle pending state correctly', async () => {
      const workosOrgId = 'org_123456789';
      const tenantId = 'tenant123';
      const state = 'pending';
      const errorMessage = null;

      mockQuery.mockResolvedValueOnce({
        rows: [{ id: tenantId, state, error_message: errorMessage }],
      });

      const result = await resolveWorkosOrgToTenant(workosOrgId);

      expect(result).toEqual({
        tenantId,
        isProvisioned: false,
        state,
        errorMessage,
      });
    });

    it('should handle provisioning state correctly', async () => {
      const workosOrgId = 'org_123456789';
      const tenantId = 'tenant123';
      const state = 'provisioning';
      const errorMessage = null;

      mockQuery.mockResolvedValueOnce({
        rows: [{ id: tenantId, state, error_message: errorMessage }],
      });

      const result = await resolveWorkosOrgToTenant(workosOrgId);

      expect(result).toEqual({
        tenantId,
        isProvisioned: false,
        state,
        errorMessage,
      });
    });
  });
});
