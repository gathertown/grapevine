export enum PermissionAudience {
  Tenant = 'tenant',
  Private = 'private',
}

export interface FileAttachment {
  name: string;
  mimetype: string;
  content: string; // Base64 encoded content
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  files?: FileAttachment[];
}

export interface QuestionResponse {
  answer: string;
  metadata?: Record<string, unknown>;
}

export interface GeneratedAnswer {
  answer: string;
  confidence?: number;
  confidenceExplanation?: string;
  responseId?: string;
}

export interface SlackEvent {
  type: string;
  channel: string;
  user?: string;
  ts: string;
  item?: {
    type: string;
    channel: string;
    ts: string;
  };
}

export interface SlackReactionEvent extends SlackEvent {
  reaction: string;
  user: string;
  item: {
    type: string;
    channel: string;
    ts: string;
  };
}

export type ReactionType = '+1' | '-1';

// Event handler types
import { TenantSlackApp } from './TenantSlackApp';
import { GenericMessageEvent } from '@slack/bolt';

export interface SayOptions {
  text?: string;
  thread_ts?: string;
  [key: string]: unknown;
}

// Basic event args for simple events (channel_created, reaction_added, etc.)
export interface BasicEventArgs<T = unknown> {
  event: T;
  tenantSlackApp: TenantSlackApp;
}

// Message event args with say function for message handling
export interface MessageEventArgs {
  message: GenericMessageEvent; // Use official Slack Bolt type
  say: (options: SayOptions) => Promise<unknown>;
  tenantSlackApp: TenantSlackApp;
}

// Event type definitions for handlers
export interface ChannelCreatedEvent {
  type: 'channel_created';
  channel: {
    id: string;
    name: string;
  };
}

export interface ReactionAddedEvent {
  type: 'reaction_added';
  user: string;
  reaction: string;
  // Some messages aren't authored by "users," like those created by incoming
  // webhooks. reaction_added events related to these messages will not
  // include an item_user. https://docs.slack.dev/reference/events/reaction_added
  item_user?: string;
  item: {
    type: 'message';
    channel: string;
    ts: string;
  };
  event_ts: string;
}

export interface ReactionRemovedEvent {
  type: 'reaction_removed';
  user: string;
  reaction: string;
  // Some messages aren't authored by "users," like those created by incoming
  // webhooks. reaction_removed events related to these messages will not
  // include an item_user. https://docs.slack.dev/reference/events/reaction_removed/
  item_user?: string;
  item: {
    type: 'message';
    channel: string;
    ts: string;
  };
  event_ts: string;
}
