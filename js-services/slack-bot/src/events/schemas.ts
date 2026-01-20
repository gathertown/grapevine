import { z } from 'zod';

/**
 * Shared Zod schemas for Slack events used by both webhook (production)
 * and Socket Mode (debug) event processing.
 *
 * These schemas are extracted from slackEventProcessor.ts to ensure
 * both production and debug modes validate events consistently.
 */

// Channel created event - matches ChannelCreatedEvent from @slack/types
export const ChannelCreatedEventSchema = z.object({
  type: z.literal('channel_created'),
  channel: z.object({
    id: z.string(),
    name: z.string(),
  }),
});

// Member joined channel event - matches MemberJoinedChannelEvent from @slack/types
export const MemberJoinedChannelEventSchema = z.object({
  type: z.literal('member_joined_channel'),
  user: z.string(),
  channel: z.string(),
});

// Member left channel event - matches MemberLeftChannelEvent from @slack/types
export const MemberLeftChannelEventSchema = z.object({
  type: z.literal('member_left_channel'),
  user: z.string(),
  channel: z.string(),
});

// Reaction added event - matches ReactionAddedEvent from @slack/types
export const ReactionAddedEventSchema = z.object({
  type: z.literal('reaction_added'),
  user: z.string(),
  reaction: z.string(),
  item_user: z.string().optional(),
  item: z.object({
    type: z.literal('message'),
    channel: z.string(),
    ts: z.string(),
  }),
  event_ts: z.string(),
});

// Reaction removed event - matches ReactionRemovedEvent from @slack/types
export const ReactionRemovedEventSchema = z.object({
  type: z.literal('reaction_removed'),
  user: z.string(),
  reaction: z.string(),
  item_user: z.string().optional(),
  item: z.object({
    type: z.literal('message'),
    channel: z.string(),
    ts: z.string(),
  }),
  event_ts: z.string(),
});

// App mention event - when bot is mentioned with @botname
export const AppMentionEventSchema = z.object({
  type: z.literal('app_mention'),
  user: z.string(),
  text: z.string().optional(),
  ts: z.string(),
  channel: z.string(),
  event_ts: z.string(),
  thread_ts: z.string().optional(),
  client_msg_id: z.string().optional(),
  team: z.string().optional(),
  blocks: z.array(z.any()).optional(),
});

// Message event - handles all Slack message types with channel_type for DM detection
export const MessageEventSchema = z.object({
  type: z.literal('message'),
  subtype: z.string().optional(), // Allow all subtypes (undefined, 'bot_message', etc.)
  event_ts: z.string(),
  team: z.string().optional(),
  channel: z.string(),
  channel_type: z.enum(['channel', 'group', 'im', 'mpim', 'app_home']), // Channel type for DM detection
  user: z.string().optional(), // Optional - bot messages don't have user
  bot_id: z.string().optional(),
  text: z.string().optional(),
  ts: z.string(),
  thread_ts: z.string().optional(),
  client_msg_id: z.string().optional(),
  parent_user_id: z.string().optional(),
  is_starred: z.boolean().optional(),
  pinned_to: z.array(z.string()).optional(),
  edited: z
    .object({
      user: z.string().optional(),
      ts: z.string(),
    })
    .optional(),
  reactions: z
    .array(
      z.object({
        name: z.string(),
        count: z.number(),
        users: z.array(z.string()),
      })
    )
    .optional(),
  files: z.array(z.any()).optional(), // File attachments
  username: z.string().optional(), // For bot messages
  icons: z.record(z.string()).optional(), // For bot messages
});

// Union of all Slack event types we handle
export const SlackEventSchema = z.discriminatedUnion('type', [
  ChannelCreatedEventSchema,
  MemberJoinedChannelEventSchema,
  MemberLeftChannelEventSchema,
  ReactionAddedEventSchema,
  ReactionRemovedEventSchema,
  AppMentionEventSchema,
  MessageEventSchema,
]);

// TypeScript types derived from schemas
export type ChannelCreatedEvent = z.infer<typeof ChannelCreatedEventSchema>;
export type MemberJoinedChannelEvent = z.infer<typeof MemberJoinedChannelEventSchema>;
export type MemberLeftChannelEvent = z.infer<typeof MemberLeftChannelEventSchema>;
export type ReactionAddedEvent = z.infer<typeof ReactionAddedEventSchema>;
export type ReactionRemovedEvent = z.infer<typeof ReactionRemovedEventSchema>;
export type AppMentionEvent = z.infer<typeof AppMentionEventSchema>;
export type MessageEvent = z.infer<typeof MessageEventSchema>;
export type SlackEvent = z.infer<typeof SlackEventSchema>;

// Helper function to get unique message identifier for deduplication
export function getMessageKey(event: SlackEvent): string | null {
  // Only message-like events can be deduplicated
  if (event.type === 'message' || event.type === 'app_mention') {
    return `${event.channel}:${event.ts}`;
  }
  return null;
}
