import { jest, describe, it, expect, beforeEach, test } from '@jest/globals';
import { joinAllowedChannels } from '../channelJoiner';

const mockSlackClient = {
  conversations: {
    list: jest.fn<() => any>(),
    join: jest.fn<(...args: any[]) => any>(),
  },
};

const mockTenantSlackApp = {
  client: mockSlackClient,
};

const mockAppManager = {
  getTenantSlackApp: jest.fn(() => Promise.resolve(mockTenantSlackApp)),
};

// Mock the tenant slack app manager
jest.mock('../tenantSlackAppManager', () => ({
  getTenantSlackAppManager: jest.fn(() => mockAppManager),
}));

// Mock the logger
jest.mock('../utils/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    error: jest.fn(),
  },
  LogContext: {
    run: jest.fn((_context: any, fn: () => any) => fn()),
  },
}));

describe('joinAllowedChannels', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('logs startup message when joining all channels', async () => {
    // Mock Slack client responses
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify the startup message was logged
    const { logger } = await import('../utils/logger');
    expect(logger.info).toHaveBeenCalledWith(
      '🔄 Starting to join all available channels for tenant test-tenant'
    );
  });

  test('logs currently joined channels count', async () => {
    // Mock Slack client responses
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify joined channels count is logged
    const { logger } = await import('../utils/logger');
    expect(logger.info).toHaveBeenCalledWith('Currently joined channels', {
      joinedChannelCount: 3,
    });
  });

  test('joins all public channels that are not already joined', async () => {
    // Mock Slack client responses
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C3',
          name: 'channel3',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C5',
          name: 'channel5',
          is_member: false,
          is_private: true,
          is_archived: false,
        }, // Private channel
        {
          id: 'C6',
          name: 'slack-connect-channel',
          is_member: false,
          is_private: false,
          is_archived: false,
          is_ext_shared: true,
        }, // Slack Connect channel
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify join is called for public channels only
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C2',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C3',
    });
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalledWith({
      channel: 'C5',
    }); // Private channel should not be joined
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalledWith({
      channel: 'C6',
    }); // Slack Connect channel should not be joined
    expect(mockSlackClient.conversations.join).toHaveBeenCalledTimes(2);
  });

  test('handles the case when no channels need to be joined', async () => {
    // Mock Slack client responses - all channels are already joined
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C3',
          name: 'channel3',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify join is not called
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalled();

    // Check that completion message was logged
    const { logger } = await import('../utils/logger');
    expect(logger.info).toHaveBeenCalledWith('✅ Channel joining process completed');
  });

  test('joins all public channels regardless of configuration', async () => {
    // Mock Slack client responses
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C3',
          name: 'channel3',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C5',
          name: 'channel5',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify join is called for all public channels that are not already joined
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C2',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C3',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C4',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C5',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledTimes(4);
  });

  test('skips private and archived channels', async () => {
    // Mock Slack client responses
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: [
        {
          id: 'C1',
          name: 'channel1',
          is_member: true,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C2',
          name: 'channel2',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C3',
          name: 'channel3',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C4',
          name: 'channel4',
          is_member: false,
          is_private: false,
          is_archived: false,
        },
        {
          id: 'C5',
          name: 'channel5',
          is_member: false,
          is_private: false,
          is_archived: true,
        }, // Archived
        {
          id: 'C6',
          name: 'channel6',
          is_member: false,
          is_private: true,
          is_archived: false,
        }, // Private
      ],
    });

    await joinAllowedChannels('test-tenant');

    // Verify we join all public, non-archived channels
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C2',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C3',
    });
    expect(mockSlackClient.conversations.join).toHaveBeenCalledWith({
      channel: 'C4',
    });
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalledWith({
      channel: 'C5',
    }); // Archived
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalledWith({
      channel: 'C6',
    }); // Private
    expect(mockSlackClient.conversations.join).toHaveBeenCalledTimes(3);
  });

  it('should handle error when joining channel', async () => {
    // Mock response
    const mockChannels = [{ id: 'C123', name: 'channel1', is_private: false, is_member: false }];

    mockSlackClient.conversations.list.mockResolvedValue({
      channels: mockChannels,
      response_metadata: { next_cursor: '' },
    });

    // Mock join to throw an error
    mockSlackClient.conversations.join.mockRejectedValue(new Error('Join failed'));

    await joinAllowedChannels('test-tenant');

    // Verify error was logged
    const { logger } = await import('../utils/logger');
    expect(logger.error).toHaveBeenCalledWith(
      'Failed to join channel channel1',
      expect.any(Error),
      {
        channelName: 'channel1',
        channelId: 'C123',
      }
    );
  });

  it('should handle error in the overall channel joining process', async () => {
    // Mock list to throw an error
    mockSlackClient.conversations.list.mockRejectedValue(new Error('API error'));

    // Verify error propagates (for SQS retry)
    await expect(joinAllowedChannels('test-tenant')).rejects.toThrow('API error');
  });

  it('should handle case when no channels are found', async () => {
    // Mock response with no channels
    mockSlackClient.conversations.list.mockResolvedValue({
      channels: null,
      response_metadata: { next_cursor: '' },
    });

    // Verify error propagates (for SQS retry)
    await expect(joinAllowedChannels('test-tenant')).rejects.toThrow(
      'No channels found or error retrieving channels'
    );
  });

  it('should handle case when already joined all channels', async () => {
    // Mock response with already joined channel
    const mockChannels = [{ id: 'C123', name: 'channel1', is_private: false, is_member: true }];

    mockSlackClient.conversations.list.mockResolvedValue({
      channels: mockChannels,
      response_metadata: { next_cursor: '' },
    });

    await joinAllowedChannels('test-tenant');

    // Verify appropriate log message
    const { logger } = await import('../utils/logger');
    expect(logger.info).toHaveBeenCalledWith(
      'Already joined all required channels for QA and additional features'
    );
    // Verify join was not called
    expect(mockSlackClient.conversations.join).not.toHaveBeenCalled();
  });
});
