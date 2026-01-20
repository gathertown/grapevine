import { describe, test, expect, jest, beforeEach } from '@jest/globals';
import { TenantSlackApp } from '../TenantSlackApp';
import { tenantConfigManager } from '../config/tenantConfigManager';

// Mock the config manager
jest.mock('../config/tenantConfigManager', () => ({
  tenantConfigManager: {
    getQaAllChannels: jest.fn(),
    getQaDisallowedChannels: jest.fn(),
    getQaAllowedChannels: jest.fn(),
    getQaSkipChannelsWithExternalGuests: jest.fn(),
  },
}));

// Type assertions for mocks
const mockGetQaAllChannels = tenantConfigManager.getQaAllChannels as jest.MockedFunction<
  typeof tenantConfigManager.getQaAllChannels
>;
const mockGetQaDisallowedChannels =
  tenantConfigManager.getQaDisallowedChannels as jest.MockedFunction<
    typeof tenantConfigManager.getQaDisallowedChannels
  >;
const mockGetQaAllowedChannels = tenantConfigManager.getQaAllowedChannels as jest.MockedFunction<
  typeof tenantConfigManager.getQaAllowedChannels
>;
const mockGetQaSkipChannelsWithExternalGuests =
  tenantConfigManager.getQaSkipChannelsWithExternalGuests as jest.MockedFunction<
    typeof tenantConfigManager.getQaSkipChannelsWithExternalGuests
  >;

describe('TenantSlackApp.shouldProcessChannel', () => {
  let tenantSlackApp: TenantSlackApp;
  let mockResolveChannelReference: jest.MockedFunction<
    (channelRef: string) => Promise<string | null>
  >;
  let mockChannelHasExternalGuests: jest.MockedFunction<(channelId: string) => Promise<boolean>>;
  const testTenantId = 'test-tenant-123';
  const testChannelId = 'C123456';
  const testChannelName = 'test-channel';

  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();

    // Create mock functions
    mockResolveChannelReference = jest.fn();
    mockChannelHasExternalGuests = jest.fn();

    // Create a minimal mock TenantSlackApp instance
    tenantSlackApp = {
      tenantId: testTenantId,
      // Use any to bypass private access restrictions in tests
      resolveChannelReference: mockResolveChannelReference,
      channelHasExternalGuests: mockChannelHasExternalGuests,
    } as any;

    // Bind the actual method we're testing
    tenantSlackApp.shouldProcessChannel =
      TenantSlackApp.prototype.shouldProcessChannel.bind(tenantSlackApp);
  });

  describe('QA_ALL_CHANNELS = true', () => {
    beforeEach(() => {
      mockGetQaAllChannels.mockResolvedValue(true);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(false);
    });

    test('Processes any channel when QA_ALL_CHANNELS is true and no disallowed list', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([]);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(tenantConfigManager.getQaAllChannels).toHaveBeenCalledWith(testTenantId);
      expect(tenantConfigManager.getQaDisallowedChannels).toHaveBeenCalledWith(testTenantId);
    });

    test('Does NOT process channel when channel ID is in disallowed list', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([testChannelId, 'C999999']);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(tenantConfigManager.getQaDisallowedChannels).toHaveBeenCalledWith(testTenantId);
    });

    test('Does NOT process channel when channel name resolves to disallowed channel ID', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([testChannelName, 'other-channel']);
      mockResolveChannelReference.mockImplementation(async (ref: string) => {
        if (ref === testChannelName) return testChannelId;
        if (ref === 'other-channel') return 'C999999';
        return null;
      });

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(mockResolveChannelReference).toHaveBeenCalledWith(testChannelName);
    });

    test('Processes channel when disallowed list contains different channels', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue(['C999999', 'other-channel']);
      mockResolveChannelReference.mockResolvedValue('C999999');

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
    });

    test('Does NOT process channel with external guests when skip setting is enabled', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([]);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(true);
      mockChannelHasExternalGuests.mockResolvedValue(true);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(tenantConfigManager.getQaSkipChannelsWithExternalGuests).toHaveBeenCalledWith(
        testTenantId
      );
      expect(mockChannelHasExternalGuests).toHaveBeenCalledWith(testChannelId);
    });

    test('Processes channel with external guests when skip setting is disabled', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([]);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(false);
      mockChannelHasExternalGuests.mockResolvedValue(true);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(mockChannelHasExternalGuests).not.toHaveBeenCalled();
    });

    test('Processes channel without external guests when skip setting is enabled', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue([]);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(true);
      mockChannelHasExternalGuests.mockResolvedValue(false);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(mockChannelHasExternalGuests).toHaveBeenCalledWith(testChannelId);
    });

    test('Handles combined disallowed list and external guests skip', async () => {
      mockGetQaDisallowedChannels.mockResolvedValue(['C999999']);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(true);
      mockChannelHasExternalGuests.mockResolvedValue(true);
      mockResolveChannelReference.mockResolvedValue('C999999');

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(mockChannelHasExternalGuests).toHaveBeenCalledWith(testChannelId);
    });
  });

  describe('QA_ALL_CHANNELS = false (allowlist mode)', () => {
    beforeEach(() => {
      mockGetQaAllChannels.mockResolvedValue(false);
    });

    test('Does NOT process any channel when allowed list is empty', async () => {
      mockGetQaAllowedChannels.mockResolvedValue([]);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(tenantConfigManager.getQaAllChannels).toHaveBeenCalledWith(testTenantId);
      expect(tenantConfigManager.getQaAllowedChannels).toHaveBeenCalledWith(testTenantId);
    });

    test('Processes channel when channel ID is in allowed list', async () => {
      mockGetQaAllowedChannels.mockResolvedValue([testChannelId, 'C999999']);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(tenantConfigManager.getQaAllowedChannels).toHaveBeenCalledWith(testTenantId);
    });

    test('Processes channel when channel name resolves to allowed channel ID', async () => {
      mockGetQaAllowedChannels.mockResolvedValue([testChannelName, 'other-channel']);
      mockResolveChannelReference.mockImplementation(async (ref: string) => {
        if (ref === testChannelName) return testChannelId;
        if (ref === 'other-channel') return 'C999999';
        return null;
      });

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(mockResolveChannelReference).toHaveBeenCalledWith(testChannelName);
    });

    test('Does NOT process channel when allowed list contains different channels', async () => {
      mockGetQaAllowedChannels.mockResolvedValue(['C999999', 'other-channel']);
      mockResolveChannelReference.mockResolvedValue('C999999');

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
    });

    test('Handles null response from resolveChannelReference', async () => {
      mockGetQaAllowedChannels.mockResolvedValue(['nonexistent-channel']);
      mockResolveChannelReference.mockResolvedValue(null);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      expect(mockResolveChannelReference).toHaveBeenCalledWith('nonexistent-channel');
    });

    test('Processes channel with mixed channel IDs and names in allowed list', async () => {
      mockGetQaAllowedChannels.mockResolvedValue(['C999999', testChannelName, 'another-channel']);
      mockResolveChannelReference.mockImplementation(async (ref: string) => {
        if (ref === 'C999999') return 'C999999';
        if (ref === testChannelName) return testChannelId;
        if (ref === 'another-channel') return 'C888888';
        return null;
      });

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
    });

    test('Ignores disallowed list when QA_ALL_CHANNELS is false (allowlist mode takes precedence)', async () => {
      // Regression test: In allowlist mode, disallowed list should be ignored
      // Channels not on the allowed list should return false, regardless of disallowed list
      mockGetQaDisallowedChannels.mockResolvedValue(['C999999']);
      mockGetQaAllowedChannels.mockResolvedValue(['C111111']);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(false);
      // Disallowed list should not even be checked in allowlist mode
      expect(mockGetQaDisallowedChannels).not.toHaveBeenCalled();
    });
  });

  describe('edge cases and error handling', () => {
    test('Handles when config manager throws errors (QA_ALL_CHANNELS)', async () => {
      mockGetQaAllChannels.mockRejectedValue(new Error('Database error'));

      await expect(tenantSlackApp.shouldProcessChannel(testChannelId)).rejects.toThrow(
        'Database error'
      );
    });

    test('Handles when config manager throws errors (allowed channels)', async () => {
      mockGetQaAllChannels.mockResolvedValue(false);
      mockGetQaAllowedChannels.mockRejectedValue(new Error('Database error'));

      await expect(tenantSlackApp.shouldProcessChannel(testChannelId)).rejects.toThrow(
        'Database error'
      );
    });

    test('Handles when resolveChannelReference throws errors', async () => {
      mockGetQaAllChannels.mockResolvedValue(false);
      mockGetQaAllowedChannels.mockResolvedValue(['problematic-channel']);
      mockResolveChannelReference.mockRejectedValue(new Error('API error'));

      await expect(tenantSlackApp.shouldProcessChannel(testChannelId)).rejects.toThrow('API error');
    });

    test('Handles when channelHasExternalGuests throws errors', async () => {
      mockGetQaAllChannels.mockResolvedValue(true);
      mockGetQaDisallowedChannels.mockResolvedValue([]);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(true);
      mockChannelHasExternalGuests.mockRejectedValue(new Error('Slack API error'));

      await expect(tenantSlackApp.shouldProcessChannel(testChannelId)).rejects.toThrow(
        'Slack API error'
      );
    });
  });

  describe('complex multi-config scenarios', () => {
    test('QA_ALL_CHANNELS=true with both disallowed list and external guests skip', async () => {
      mockGetQaAllChannels.mockResolvedValue(true);
      mockGetQaDisallowedChannels.mockResolvedValue(['C111111', 'banned-channel']);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(true);
      mockResolveChannelReference.mockImplementation(async (ref: string) => {
        if (ref === 'banned-channel') return 'C111111';
        return null;
      });
      mockChannelHasExternalGuests.mockResolvedValue(false);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(mockChannelHasExternalGuests).toHaveBeenCalledWith(testChannelId);
    });

    test('Empty disallowed list does not cause early return in QA_ALL_CHANNELS mode', async () => {
      mockGetQaAllChannels.mockResolvedValue(true);
      mockGetQaDisallowedChannels.mockResolvedValue([]);
      mockGetQaSkipChannelsWithExternalGuests.mockResolvedValue(false);

      const result = await tenantSlackApp.shouldProcessChannel(testChannelId);

      expect(result).toEqual(true);
      expect(mockResolveChannelReference).not.toHaveBeenCalled();
      expect(mockChannelHasExternalGuests).not.toHaveBeenCalled();
    });
  });
});
