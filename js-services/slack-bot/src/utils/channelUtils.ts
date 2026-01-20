import type { Channel } from '@slack/web-api/dist/response/ConversationsInfoResponse';

/**
 * Determines if the bot should join a given channel based on our joining criteria
 */
export function shouldJoinChannel(channel: Channel): boolean {
  // Only join channels that meet ALL criteria:
  // - Not already a member
  // - Public channels only (no private channels)
  // - Not archived
  // - Not a Slack Connect external shared channel
  return (
    !channel.is_member && !channel.is_private && !channel.is_archived && !channel.is_ext_shared
  );
}
