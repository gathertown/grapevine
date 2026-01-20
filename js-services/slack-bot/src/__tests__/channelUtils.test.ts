import { describe, test, expect } from '@jest/globals';
import { shouldJoinChannel } from '../utils/channelUtils';
import type { Channel } from '@slack/web-api/dist/response/ConversationsInfoResponse';

describe('shouldJoinChannel', () => {
  test('should join public channel when not a member, not archived, and not Slack Connect', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'test-channel',
      is_member: false,
      is_private: false,
      is_archived: false,
      is_ext_shared: false,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(true);
  });

  test('should not join channel if already a member', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'test-channel',
      is_member: true,
      is_private: false,
      is_archived: false,
      is_ext_shared: false,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(false);
  });

  test('should not join private channel', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'private-channel',
      is_member: false,
      is_private: true,
      is_archived: false,
      is_ext_shared: false,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(false);
  });

  test('should not join archived channel', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'archived-channel',
      is_member: false,
      is_private: false,
      is_archived: true,
      is_ext_shared: false,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(false);
  });

  test('should not join Slack Connect external shared channel', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'slack-connect-channel',
      is_member: false,
      is_private: false,
      is_archived: false,
      is_ext_shared: true,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(false);
  });

  test('should not join channel with multiple exclusion criteria', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'complex-channel',
      is_member: true,
      is_private: true,
      is_archived: true,
      is_ext_shared: true,
    };

    expect(shouldJoinChannel(channel as Channel)).toBe(false);
  });

  test('should handle channel with undefined is_ext_shared (backward compatibility)', () => {
    const channel: Partial<Channel> = {
      id: 'C123',
      name: 'legacy-channel',
      is_member: false,
      is_private: false,
      is_archived: false,
      // is_ext_shared is undefined (older API responses)
    };

    // Should still work - undefined is falsy, so !undefined is true
    expect(shouldJoinChannel(channel as Channel)).toBe(true);
  });
});
