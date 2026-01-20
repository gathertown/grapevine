import { describe, test, expect, jest, beforeEach } from '@jest/globals';
import { TenantSlackApp } from '../TenantSlackApp';
import { tenantConfigManager } from '../config/tenantConfigManager';

// Mock the config manager
jest.mock('../config/tenantConfigManager', () => ({
  tenantConfigManager: {
    getQaSkipMentionsByNonMembers: jest.fn(),
  },
}));

// Type assertion for mock
const mockGetQaSkipMentionsByNonMembers =
  tenantConfigManager.getQaSkipMentionsByNonMembers as jest.MockedFunction<
    typeof tenantConfigManager.getQaSkipMentionsByNonMembers
  >;

describe('TenantSlackApp.shouldProcessMentionFromUser', () => {
  let tenantSlackApp: TenantSlackApp;
  let mockIsFullSlackMember: jest.MockedFunction<(userId: string) => Promise<boolean>>;
  const mockTenantId = 'test-tenant-123';
  const mockChannelId = 'C123456';
  const mockUserId = 'U789012';

  beforeEach(() => {
    jest.clearAllMocks();

    // Create mock function
    mockIsFullSlackMember = jest.fn();

    // Create a minimal mock TenantSlackApp instance
    tenantSlackApp = {
      tenantId: mockTenantId,
      // Use any to bypass private access restrictions in tests
      isFullSlackMember: mockIsFullSlackMember,
    } as any;

    // Bind the actual method we're testing
    tenantSlackApp.shouldProcessMentionFromUser =
      TenantSlackApp.prototype.shouldProcessMentionFromUser.bind(tenantSlackApp);
  });

  describe('when skip mentions by non-members is disabled', () => {
    test('should allow mentions from anyone', async () => {
      mockGetQaSkipMentionsByNonMembers.mockResolvedValue(false);

      const result = await tenantSlackApp.shouldProcessMentionFromUser(mockUserId, mockChannelId);

      expect(result).toBe(true);
      expect(tenantConfigManager.getQaSkipMentionsByNonMembers).toHaveBeenCalledWith(mockTenantId);
    });
  });

  describe('when skip mentions by non-members is enabled', () => {
    test('should block mentions from guest users', async () => {
      mockGetQaSkipMentionsByNonMembers.mockResolvedValue(true);
      mockIsFullSlackMember.mockResolvedValue(false);

      const result = await tenantSlackApp.shouldProcessMentionFromUser(mockUserId, mockChannelId);

      expect(result).toBe(false);
      expect(mockIsFullSlackMember).toHaveBeenCalledWith(mockUserId);
    });

    test('should allow mentions from full members', async () => {
      mockGetQaSkipMentionsByNonMembers.mockResolvedValue(true);
      mockIsFullSlackMember.mockResolvedValue(true);

      const result = await tenantSlackApp.shouldProcessMentionFromUser(mockUserId, mockChannelId);

      expect(result).toBe(true);
    });
  });
});
