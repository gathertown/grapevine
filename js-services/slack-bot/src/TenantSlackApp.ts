import { App } from '@slack/bolt';
import { WebClient } from '@slack/web-api';
import { SSMClient } from '@corporate-context/backend-common';
import { GeneratedAnswer, Message, PermissionAudience } from './types';
import { config } from './config';
import { tenantConfigManager } from './config/tenantConfigManager';
import axios from 'axios';
import axiosRetry, { exponentialDelay } from 'axios-retry';
import { Readable } from 'stream';
import { MessageElement } from '@slack/web-api/dist/response/ConversationsHistoryResponse';
import type { Channel } from '@slack/web-api/dist/response/ConversationsInfoResponse';
import { logger, LogContext } from './utils/logger';
import { formatTextForSlack } from './utils/textFormatting';
import { getAnalyticsTracker } from './services/analyticsTracker';
import type { KnownBlock, Block } from '@slack/web-api';

// Configure axios with retry logic following gather-town-v2 pattern
axiosRetry(axios, {
  retryDelay: (retryCount, error) => exponentialDelay(retryCount, error, 1000),
  retries: 5,
});

type AskAgentToolName = 'ask_agent' | 'ask_agent_fast';
type TriageAgentToolName = 'ask_agent' | 'get_document';

interface BackendRequestOptions {
  previousResponseId?: string;
  channelId?: string;
  permissionAudience?: PermissionAudience;
  nonBillable?: boolean;
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high';
  verbosity?: 'low' | 'medium' | 'high';
  writeTools?: string[];
  outputFormat?: 'slack' | 'markdown';
}

interface AskAgentRequestOptions extends BackendRequestOptions {
  toolName?: AskAgentToolName | TriageAgentToolName;
}

interface PreparedBackendRequest {
  userPrompt: string;
  files?: Message['files'];
  userEmail: string;
  userName: string;
  options: Required<Pick<BackendRequestOptions, 'nonBillable'>> &
    Omit<BackendRequestOptions, 'nonBillable'>;
}

interface SendResponseOptions {
  isPreliminary?: boolean;
  replaceMessageTs?: string;
  deferReactionCleanup?: boolean;
  skipAnalytics?: boolean;
  skipFeedback?: boolean;
  skipMirroring?: boolean;
}

// Stream processing helper from gather-town-v2
const streamToBuffer = async (stream: Readable): Promise<Buffer> =>
  new Promise((resolve, reject) => {
    const chunks: Uint8Array[] = [];
    stream.on('data', (chunk: Uint8Array) => chunks.push(chunk));
    stream.once('error', reject);
    stream.once('end', () => resolve(Buffer.concat(chunks)));
  });

const createWebClient = (botToken: string) => {
  return new WebClient(botToken, {
    // CAREFUL - we don't want to spend too long on retries (for network / 5xx errors), otherwise pods can get stuck waiting
    // and risk the health of the slackbot queue. A related incident on 9/26/25 happened b/c we were overusing `conversations.replies`
    // and had many pods stuck waiting 15mins per loop for rate-limit backoffs, for many loops.
    retryConfig: {
      retries: 2,
      maxTimeout: 5000,
      maxRetryTime: 5000,
    },
    // See warning above - do NOT backoff for rate-limited calls because it can a very long (e.g. 15 mins) wait.
    // By default, the Slack client parses the `Retry-After` header on 429s and sleeps for that duration.
    rejectRateLimitedCalls: true,
  });
};

export class TenantSlackApp {
  // Cache for channel name to ID resolution to avoid repeated API calls
  private channelResolutionCache = new Map<string, string>();

  private constructor(
    public readonly tenantId: string,
    public readonly app: App,
    public readonly client: WebClient,
    public readonly botToken: string,
    public readonly botId: string,
    public readonly workspaceTeamId: string
  ) {}

  static async create(tenantId: string, ssmClient: SSMClient): Promise<TenantSlackApp> {
    return LogContext.run({ tenant_id: tenantId }, async () => {
      logger.info('Creating Slack app for tenant', { operation: 'tenant-app-create' });

      // Fetch tenant-specific credentials from SSM
      const [botToken, signingSecret] = await Promise.all([
        ssmClient.getSlackToken(tenantId),
        ssmClient.getSlackSigningSecret(tenantId),
      ]);

      if (!botToken || !signingSecret) {
        throw new Error(`Missing Slack credentials for tenant ${tenantId}`);
      }

      // Create the Slack app instance
      // Note: We're not using Socket Mode for tenant apps, only for debug mode
      const app = new App({
        token: botToken,
        signingSecret,
        socketMode: false, // Tenant apps don't use socket mode
        deferInitialization: true,
      });

      await app.init();

      // Create a WebClient instance for this tenant
      const client = createWebClient(botToken);

      // Get the bot ID and workspace team ID for this tenant
      let botId = '';
      let workspaceTeamId = '';
      try {
        const authResponse = await client.auth.test();
        if (authResponse.user_id) {
          botId = authResponse.user_id as string;
          logger.info(`Bot ID retrieved: ${botId}`, { operation: 'bot-id-retrieved', botId });
        }
        if (authResponse.team_id) {
          workspaceTeamId = authResponse.team_id as string;
          logger.info(`Workspace team ID retrieved: ${workspaceTeamId}`, {
            operation: 'workspace-team-id-retrieved',
            workspaceTeamId,
          });
        }
      } catch (error) {
        logger.error(`Failed to get bot ID and team ID for tenant ${tenantId}`, error, {
          tenantId,
          operation: 'bot-id-retrieval',
        });
        // Continue without bot ID/team ID - some features may not work
      }

      logger.info('Slack app ready for tenant', { operation: 'tenant-app-ready' });

      return new TenantSlackApp(tenantId, app, client, botToken, botId, workspaceTeamId);
    });
  }

  /**
   * Create a TenantSlackApp for debug mode using environment variables instead of SSM
   */
  static async createForDebug(tenantId: string): Promise<TenantSlackApp> {
    return LogContext.run({ tenant_id: tenantId }, async () => {
      logger.info('Creating debug Slack app for tenant', { operation: 'debug-app-create' });

      // For debug mode, read credentials directly from environment variables
      const botToken = process.env.SLACK_BOT_TOKEN;
      const signingSecret = process.env.SLACK_SIGNING_SECRET;
      const appToken = process.env.SLACK_APP_TOKEN;

      if (!botToken || !signingSecret) {
        throw new Error(
          `Missing Slack credentials in environment variables. Required: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET`
        );
      }

      // Create the Slack app instance with Socket Mode for debug if app token is available
      const app = new App({
        token: botToken,
        signingSecret,
        socketMode: !!appToken, // Enable Socket Mode if app token is provided
        appToken,
        deferInitialization: true,
      });

      await app.init();

      // Create a WebClient instance
      const client = createWebClient(botToken);

      // Get the bot ID and workspace team ID
      let botId = '';
      let workspaceTeamId = '';
      try {
        const authResponse = await client.auth.test();
        if (authResponse.user_id) {
          botId = authResponse.user_id as string;
          logger.debug(`Debug bot ID retrieved for tenant ${tenantId}: ${botId}`, {
            tenant_id: tenantId,
            botId,
          });
        }
        if (authResponse.team_id) {
          workspaceTeamId = authResponse.team_id as string;
          logger.debug(
            `Debug workspace team ID retrieved for tenant ${tenantId}: ${workspaceTeamId}`,
            {
              tenant_id: tenantId,
              workspaceTeamId,
            }
          );
        }
      } catch (error) {
        logger.error(`Failed to get bot ID and team ID for debug tenant ${tenantId}`, error, {
          tenant_id: tenantId,
        });
        // Continue without bot ID/team ID - some features may not work
      }

      logger.info(`Debug Slack app ready for tenant: ${tenantId}`);

      return new TenantSlackApp(tenantId, app, client, botToken, botId, workspaceTeamId);
    });
  }

  /**
   * Resolve a channel reference (name or ID) to a channel ID
   * @param channelRef Channel name or ID to resolve
   */
  private async resolveChannelReference(channelRef: string): Promise<string | null> {
    // If it looks like a channel ID (starts with C), return as-is
    if (channelRef.startsWith('C')) {
      return channelRef;
    }

    // Check cache first
    const cachedValue = this.channelResolutionCache.get(channelRef);
    if (cachedValue !== undefined) {
      return cachedValue;
    }

    try {
      // For tenant-specific clients, always fetch fresh channel list
      // Get all channels with pagination
      const allChannels: Channel[] = [];
      let cursor: string | undefined;

      do {
        const response = await this.client.conversations.list({
          types: 'public_channel,private_channel',
          exclude_archived: true,
          limit: 1000,
          cursor,
        });

        if (response.channels) {
          // Filter out channels without IDs and cast to SlackChannel
          const validChannels = response.channels
            .filter((channel) => channel.id)
            .map((channel) => channel as Channel);
          allChannels.push(...validChannels);
        }

        cursor = response.response_metadata?.next_cursor;
      } while (cursor);

      const channel = allChannels.find((c: Channel) => c.name === channelRef);
      if (channel && channel.id) {
        // Cache the result with appropriate key
        this.channelResolutionCache.set(channelRef, channel.id);
        return channel.id;
      }

      logger.warn(`Could not resolve channel reference: ${channelRef}`, { channelRef });
      return null;
    } catch (error) {
      logger.error(`Error resolving channel reference ${channelRef}`, error, { channelRef });
      return null;
    }
  }

  async shouldProcessChannel(channelId: string): Promise<boolean> {
    // For Q&A functionality, use tenant-specific configuration from database
    const qaAllChannels = await tenantConfigManager.getQaAllChannels(this.tenantId);
    if (qaAllChannels) {
      // check if this channel is explicitly disallowed
      const qaDisallowedChannels = await tenantConfigManager.getQaDisallowedChannels(this.tenantId);
      if (qaDisallowedChannels.length > 0) {
        // Check if channel ID is directly in the disallowed list
        if (qaDisallowedChannels.includes(channelId)) {
          return false;
        }

        // Also check if any channel names in the disallowed list resolve to this channel ID
        for (const channelRef of qaDisallowedChannels) {
          const resolvedId = await this.resolveChannelReference(channelRef);
          if (resolvedId === channelId) {
            return false;
          }
        }
      }

      // Check if we should skip channels with external guests
      const skipChannelsWithExternalGuests =
        await tenantConfigManager.getQaSkipChannelsWithExternalGuests(this.tenantId);
      if (skipChannelsWithExternalGuests) {
        const hasExternalGuests = await this.channelHasExternalGuests(channelId);
        if (hasExternalGuests) {
          logger.info(
            `[shouldProcessChannel] Skipping channel ${channelId} due to external guests`,
            {
              channelId,
              operation: 'shouldProcessChannel',
            }
          );
          return false;
        }
      }

      return true;
    }

    // check if this channel is explicitly enabled
    const qaAllowedChannels = await tenantConfigManager.getQaAllowedChannels(this.tenantId);
    if (qaAllowedChannels.length > 0) {
      // Check if channel ID is directly in the list
      if (qaAllowedChannels.includes(channelId)) {
        return true;
      }

      // Also check if any channel names in the list resolve to this channel ID
      for (const channelRef of qaAllowedChannels) {
        const resolvedId = await this.resolveChannelReference(channelRef);
        if (resolvedId === channelId) {
          return true;
        }
      }
    }

    return false;
  }

  /**
   * Determine if we should process a mention from this user.
   * Checks if mentions by non-members are blocked (config setting).
   *
   * @param userId - The Slack user ID who mentioned the bot
   * @param channelId - The Slack channel ID (for logging)
   * @returns True if we should process the mention, false otherwise
   */
  async shouldProcessMentionFromUser(userId: string, channelId: string): Promise<boolean> {
    // Check if tenant has enabled skipping mentions by non-members
    const skipMentionsByNonMembers = await tenantConfigManager.getQaSkipMentionsByNonMembers(
      this.tenantId
    );

    if (!skipMentionsByNonMembers) {
      // Tenant allows mentions from everyone
      logger.debug('Mentions by non-members allowed by tenant config', {
        userId,
        channelId,
        tenantId: this.tenantId,
        operation: 'shouldProcessMentionFromUser',
      });
      return true;
    }

    // Check if the user is a full member (not guest/restricted/external)
    const isFullMember = await this.isFullSlackMember(userId);

    if (!isFullMember) {
      logger.info('[shouldProcessMentionFromUser] Skipping mention from non-member user', {
        userId,
        channelId,
        tenantId: this.tenantId,
        operation: 'shouldProcessMentionFromUser',
      });
      return false; // User is a guest/restricted user - skip
    }

    return true; // User is a full member - allow
  }

  async getUserEmail(userId: string): Promise<string> {
    try {
      const result = await this.client.users.info({ user: userId });

      // Check if this is a bot user
      if (result.user?.is_bot) {
        throw new Error(`User ${userId} is a bot and doesn't have an email address`);
      }

      if (!result.ok || !result.user?.profile?.email) {
        throw new Error(`Could not find email for user ${userId}`);
      }
      return result.user.profile.email;
    } catch (error) {
      logger.error('Error fetching user email', error, { userId });
      throw error;
    }
  }

  /**
   * Add eye reaction to indicate processing is starting
   */
  async addProcessingReaction(channel: string, timestamp: string): Promise<void> {
    try {
      await this.client.reactions.add({
        channel,
        timestamp,
        name: 'eyes',
      });
    } catch (error) {
      logger.warn('Could not add eyes reaction', {
        error: (error as Error).message,
        channelId: channel,
        messageTs: timestamp,
      });
      // Continue processing even if reaction fails
    }
  }

  /**
   * Remove eye reaction to indicate processing is complete
   */
  async removeProcessingReaction(channel: string, timestamp: string): Promise<void> {
    try {
      await this.client.reactions.remove({
        channel,
        timestamp,
        name: 'eyes',
      });
    } catch (error) {
      logger.warn('Could not remove eyes reaction', {
        error: (error as Error).message,
        channelId: channel,
        messageTs: timestamp,
      });
      // Continue even if reaction removal fails
    }
  }

  /**
   * Add feedback reactions (thumbs up and down) to a message
   */
  async addFeedbackReactions(channel: string, timestamp: string): Promise<void> {
    try {
      await Promise.all([
        this.client.reactions.add({
          channel,
          timestamp,
          name: '+1',
        }),
        this.client.reactions.add({
          channel,
          timestamp,
          name: '-1',
        }),
      ]);
    } catch (error) {
      logger.warn('Could not add feedback reactions', {
        error: (error as Error).message,
        channelId: channel,
        messageTs: timestamp,
      });
      // Continue even if adding reactions fails
    }
  }

  /**
   * Get the channel name for display purposes
   */
  async getChannelName(channelId: string): Promise<string> {
    try {
      const response = await this.client.conversations.info({
        channel: channelId,
      });

      return response.channel?.name || channelId;
    } catch (error) {
      logger.error('[getChannelName] Error getting channel name', error, { channelId });
      return channelId; // Fallback to channel ID
    }
  }

  /**
   * Get the user name for display purposes
   */
  async getUserName(userId: string): Promise<string> {
    try {
      const response = await this.client.users.info({
        user: userId,
      });

      interface SlackUser {
        display_name?: string;
        real_name?: string;
        name?: string;
      }
      const user = response.user as SlackUser;
      return user?.display_name || user?.real_name || user?.name || userId;
    } catch (error) {
      logger.error('[getUserName] Error getting user name', error, { userId });
      return userId; // Fallback to user ID
    }
  }

  /**
   * Get the team's Slack domain for generating proper links
   */
  private async getTeamDomain(): Promise<string | null> {
    try {
      const teamInfo = await this.client.team.info();

      // The domain is in team.domain
      if (teamInfo.team && typeof teamInfo.team === 'object' && 'domain' in teamInfo.team) {
        return (teamInfo.team as { domain: string }).domain;
      }

      logger.error('[getTeamDomain] Team domain not found in team.info response');
      return null;
    } catch (error) {
      logger.error('[getTeamDomain] Error getting team domain', error);
      return null;
    }
  }

  /**
   * Get DM channel ID for a user
   */
  private async getDMChannelForUser(userId: string): Promise<string> {
    const response = await this.client.conversations.open({ users: userId });
    if (!response.channel?.id) {
      throw new Error(`Could not open DM channel with user ${userId}`);
    }
    return response.channel.id;
  }

  /**
   * Check if a user is a full member of the Slack workspace or a bot
   * (not a guest, restricted user, or external Slack Connect user)
   */
  async isFullSlackMember(userId: string): Promise<boolean> {
    try {
      // Checking if user is a full workspace member

      const result = await this.client.users.info({ user: userId });

      if (!result.ok || !result.user) {
        logger.error(`[isFullSlackMember] Failed to get user info for ${userId}`, {
          userId,
        });
        return false;
      }

      const user = result.user;

      // Check if this is a bot user - bots are not considered external guests
      if (user.is_bot) {
        logger.info(`[isFullSlackMember] User ${userId} is a bot - treating as full member`, {
          userId,
        });
        return true;
      }

      // Check various guest/restricted flags
      const isRestricted = user.is_restricted || false;
      const isUltraRestricted = user.is_ultra_restricted || false;
      const isStranger = user.is_stranger || false;

      // Check user restrictions and team membership
      // A user is external if:
      // 1. They have is_stranger flag set, OR
      // 2. Their team_id doesn't match the workspace team_id (from another workspace)
      const userTeamId = user.team_id || '';
      const isFromDifferentWorkspace =
        this.workspaceTeamId && userTeamId && userTeamId !== this.workspaceTeamId;

      // User is a full member if they are NOT any type of guest or external user
      const isFullMember =
        !isRestricted && !isUltraRestricted && !isStranger && !isFromDifferentWorkspace;

      logger.info(
        `[isFullSlackMember] User ${userId} is ${isFullMember ? 'FULL MEMBER ✅' : 'GUEST/EXTERNAL ❌'}`,
        {
          userId,
          isFullMember,
          isRestricted,
          isUltraRestricted,
          isStranger,
          isFromDifferentWorkspace,
          userTeamId,
          workspaceTeamId: this.workspaceTeamId,
        }
      );

      return isFullMember;
    } catch (error) {
      logger.error('[isFullSlackMember] Error checking member status', error, {
        tenantId: this.tenantId,
        userId,
      });
      // Fail closed for security
      return false;
    }
  }

  /**
   * Check if a channel contains external guests or restricted users, or is a Slack Connect channel
   */
  async channelHasExternalGuests(channelId: string): Promise<boolean> {
    try {
      logger.debug(`[channelHasExternalGuests] Checking channel ${channelId} for external guests`, {
        tenantId: this.tenantId,
        channelId,
      });

      // First check if the channel is a Slack Connect (externally shared) channel
      const channelInfo = await this.client.conversations.info({ channel: channelId });
      if (channelInfo.channel?.is_ext_shared) {
        logger.info(`[channelHasExternalGuests] Channel ${channelId} is a Slack Connect channel`, {
          tenantId: this.tenantId,
          channelId,
        });
        return true;
      }

      // Get all members of the channel
      const result = await this.client.conversations.members({ channel: channelId });

      if (!result.ok || !result.members) {
        logger.error(
          `[channelHasExternalGuests] Failed to get channel members for ${channelId}`,
          undefined,
          { tenantId: this.tenantId, channelId }
        );
        return false; // Fail open to not block functionality
      }

      // Check each member to see if they are a full member
      for (const userId of result.members) {
        const isFullMember = await this.isFullSlackMember(userId);
        if (!isFullMember) {
          logger.info(
            `[channelHasExternalGuests] Channel ${channelId} has external guests - found user ${userId}`,
            {
              tenantId: this.tenantId,
              channelId,
              userId,
            }
          );
          return true;
        }
      }

      logger.debug(`[channelHasExternalGuests] Channel ${channelId} has no external guests`, {
        tenantId: this.tenantId,
        channelId,
      });
      return false;
    } catch (error) {
      logger.error(`[channelHasExternalGuests] Error checking channel ${channelId}`, error, {
        tenantId: this.tenantId,
        channelId,
      });
      // Fail open to not break functionality
      return false;
    }
  }

  /**
   * Send a polite DM to guest/external users explaining the restriction
   * and also reply to their original message
   */
  async sendGuestUserNotification(
    userId: string,
    channel?: string,
    messageTs?: string,
    threadTs?: string
  ): Promise<void> {
    try {
      // Send a DM
      try {
        const dmChannelId = await this.getDMChannelForUser(userId);
        await this.postMessage({
          channel: dmChannelId,
          text: "Hi! This bot is currently available only for full workspace members. Guest users and external collaborators (Slack Connect) don't have access to this feature. If you need assistance, please reach out to a full workspace member.",
        });
        logger.info(`[sendGuestUserNotification] Sent DM to user ${userId}`, {
          tenantId: this.tenantId,
          userId,
        });
      } catch (dmError) {
        logger.error('[sendGuestUserNotification] Failed to send DM', dmError, {
          tenantId: this.tenantId,
          userId,
        });
      }

      // Also reply to the original message if we have the context
      if (channel && messageTs) {
        await this.postMessage({
          channel,
          text: `<@${userId}> Sorry, this bot is currently available only for full workspace members. Guest and external users don't have access. I've sent you a DM with more information.`,
          thread_ts: threadTs || messageTs, // Reply in thread if it's a thread message
        });
        logger.info(`[sendGuestUserNotification] Replied to message in channel ${channel}`, {
          tenantId: this.tenantId,
          channelId: channel,
        });
      }
    } catch (error) {
      logger.error('[sendGuestUserNotification] Error sending guest user notification', error, {
        tenantId: this.tenantId,
        userId,
        channel,
      });
      // Don't throw - notification failure shouldn't break the main flow
    }
  }

  /**
   * Get all messages from a thread for context
   * Slack has rate limits on the conversations.thread api, so please be mindful. If you can get the same
   * information without querying slack, please do!
   */
  async getThreadContext(
    channel: string,
    threadTs: string
  ): Promise<{
    messages: Message[];
    messageElements: MessageElement[];
    contextText: string;
  }> {
    try {
      logger.debug(
        `[getThreadContext] Getting all messages from thread ${threadTs} in channel ${channel} with conversations.replies()...`,
        {
          threadTs,
          channelId: channel,
        }
      );

      // Get all replies in the thread (no limit to get entire thread)
      const response = await this.client.conversations.replies({
        channel,
        ts: threadTs,
        // Remove limit to get all messages in the thread
      });

      if (!response.messages || response.messages.length === 0) {
        logger.debug('[getThreadContext] No messages found in thread', {
          channelId: channel,
          threadTs,
        });
        return { messages: [], messageElements: [], contextText: '' };
      }

      interface SlackMessage {
        text?: string;
        subtype?: string;
        ts?: string;
        bot_id?: string;
        user?: string;
        blocks?: Array<{
          type: string;
          text?: { type: string; text: string };
          elements?: Array<{ type: string; text?: string }>;
        }>;
      }

      // Helper to extract text from Slack blocks
      const extractTextFromBlocks = (blocks?: SlackMessage['blocks']): string => {
        if (!blocks || blocks.length === 0) return '';
        return blocks
          .map((block) => {
            if (block.type === 'section' && block.text?.text) {
              return block.text.text;
            }
            return '';
          })
          .filter((text) => text)
          .join('\n');
      };

      // Sort by timestamp to get chronological order
      const allMessages = response.messages
        .filter((msg) => msg.text || (msg as SlackMessage).blocks) // Keep messages with text or blocks
        .sort((a, b) => parseFloat(a.ts || '0') - parseFloat(b.ts || '0'));

      // Take all messages except the most recent one (which is the mention)
      const contextMessages = allMessages.slice(0, -1); // Exclude the last message (the mention)

      logger.debug(`[getThreadContext] Found ${contextMessages.length} context messages`, {
        channelId: channel,
        threadTs,
        messageCount: contextMessages.length,
      });

      // Convert to Message format and create context text
      const { stripMessageHeader } = await import('./common');
      const messages: Message[] = contextMessages.map((msg) => {
        const slackMsg = msg as SlackMessage;
        // Prefer text from blocks if available, otherwise use msg.text
        const blockText = extractTextFromBlocks(slackMsg.blocks);
        const messageText = blockText || msg.text || '';

        return {
          role: slackMsg.bot_id ? 'assistant' : ('user' as const),
          content: stripMessageHeader(messageText),
          ts: msg.ts,
        };
      });

      // Format context text for debugging
      const contextText = contextMessages
        .map(
          (msg, index) =>
            `${index + 1}. ${
              msg.user || ((msg as SlackMessage).bot_id ? 'Bot' : 'User')
            }: ${stripMessageHeader(msg.text || '')}`
        )
        .join('\n');

      return { messages, messageElements: response.messages, contextText };
    } catch (error) {
      logger.error('[getThreadContext] Error getting thread context', error, {
        channelId: channel,
        threadTs,
      });
      return { messages: [], messageElements: [], contextText: '' };
    }
  }

  private async prepareQABackendRequest(
    message: Message,
    userId: string,
    options: BackendRequestOptions = {}
  ): Promise<PreparedBackendRequest> {
    const userEmail = await this.getUserEmail(userId).catch(() => userId);
    const userName = await this.getUserName(userId).catch(() => 'Unknown User');

    let userPrompt = message.content || '';
    const files = message.files || [];

    userPrompt = `The user asking this question is: ${userName} (${userEmail}).\n\n${userPrompt}`;

    const channelId = options.channelId;
    if (channelId) {
      try {
        const channelName = await this.getChannelName(channelId);
        userPrompt = `You are in SLACK CHANNEL:${channelName} (${channelId}). Utilize the channel and its contents as context to answering the query.

IMPORTANT: If you retrieve Slack messages from this channel during your search, do NOT use the current thread/conversation you are responding in as evidence for your answer. The user's question was asked IN this thread, so using the thread content to answer would be circular and confusing. Follow this constraint silently - do not mention it in your answer.

CRITICAL: Do NOT cite your own previous responses as evidence. All factual claims must be supported by citations to actual source documents (GitHub, Slack messages from other threads/channels, Notion, etc.), never by your own prior answers. Your previous responses may contain reasoning and conclusions, but those must have been based on underlying evidence - cite that underlying evidence directly. Follow this constraint silently - do not mention it in your answer.

${userPrompt}`;
      } catch {
        logger.warn(
          `[generateAnswerFromBackend] Could not get channel name for ${channelId}, using original prompt`
        );
      }
    }

    userPrompt = `
IMPORTANT: Include a confidence level from 0% to 100% with your answer and explain why.
Use the following format and place it at the very end of your answer, on the last line:
<confidence><level>100</level><why>This is the explanation for the given confidence level</why></confidence>
Make sure not to include any other tags with the confidence level!

${userPrompt}`;

    logger.info(`[generateAnswerFromBackend] Processing query for user: ${userEmail}`, {
      tenantId: this.tenantId,
      userEmail,
    });
    if (files.length > 0) {
      logger.debug(`[generateAnswerFromBackend] Processing ${files.length} files`, {
        tenantId: this.tenantId,
        fileCount: files.length,
      });
    }

    const resolvedOptions: PreparedBackendRequest['options'] = {
      ...options,
      nonBillable: options.nonBillable ?? !!options.previousResponseId,
    };

    return {
      userPrompt,
      files: files.length > 0 ? files : undefined,
      userEmail,
      userName,
      options: resolvedOptions,
    };
  }

  private async executeBackendRequest(
    prepared: PreparedBackendRequest,
    toolName: AskAgentToolName | TriageAgentToolName,
    overrides: Partial<BackendRequestOptions> = {}
  ): Promise<GeneratedAnswer | null> {
    try {
      const options: BackendRequestOptions = {
        ...prepared.options,
        ...overrides,
      };
      const nonBillable = options.nonBillable ?? prepared.options.nonBillable ?? false;

      const { makeBackendRequest } = await import('./common');
      const response = await makeBackendRequest(
        this.tenantId,
        prepared.userPrompt,
        prepared.userEmail,
        prepared.files,
        options.previousResponseId,
        options.permissionAudience,
        nonBillable,
        options.reasoningEffort,
        options.verbosity,
        toolName,
        undefined, // disableTools
        options.writeTools,
        options.outputFormat
      );

      if (!response) {
        logger.warn('[generateAnswerFromBackend] No response from makeBackendRequest', {
          tenantId: this.tenantId,
        });
        return null;
      }

      const { answer, confidence, confidenceExplanation } = this.stripConfidenceTags(
        response.answer,
        true
      );

      if (confidence !== undefined) {
        logger.info(
          `[generateAnswerFromBackend] Extracted confidence information, confidence: ${confidence}%`,
          {
            tenantId: this.tenantId,
            confidence,
            explanation: confidenceExplanation,
            userEmail: prepared.userEmail,
          }
        );
      }

      return { answer, confidence, confidenceExplanation, responseId: response.response_id };
    } catch (error) {
      const { handleBackendError } = await import('./common');
      handleBackendError(error);
      return null;
    }
  }

  /**
   * Execute a streaming backend request using the /v1/ask/stream endpoint.
   * Logs each event as it arrives and returns the final answer.
   * @param prepared - Prepared backend request with user prompt and options
   * @param overrides - Optional overrides for request options
   * @param onEvent - Optional callback for each streaming event (for progress updates)
   */
  private async executeBackendRequestStreaming(
    prepared: PreparedBackendRequest,
    overrides: Partial<BackendRequestOptions> = {},
    onEvent?: (event: import('./common').StreamEvent) => void
  ): Promise<GeneratedAnswer | null> {
    try {
      const options: BackendRequestOptions = {
        ...prepared.options,
        ...overrides,
      };
      const nonBillable = options.nonBillable ?? prepared.options.nonBillable ?? false;

      const { makeBackendRequestStreaming } = await import('./common');
      const response = await makeBackendRequestStreaming(
        this.tenantId,
        prepared.userPrompt,
        prepared.userEmail,
        prepared.files,
        options.previousResponseId,
        options.permissionAudience,
        nonBillable,
        (event) => {
          // Log each event with structured logging
          logger.info('[executeBackendRequestStreaming] Agent event', {
            tenantId: this.tenantId,
            eventType: event.type,
            operation: 'streaming-agent-event',
          });
          // Call external event callback if provided
          if (onEvent) {
            onEvent(event);
          }
        }
      );

      if (!response) {
        logger.warn('[executeBackendRequestStreaming] No response from streaming request', {
          tenantId: this.tenantId,
        });
        return null;
      }

      const { answer, confidence, confidenceExplanation } = this.stripConfidenceTags(
        response.answer,
        true
      );

      if (confidence !== undefined) {
        logger.info(`[executeBackendRequestStreaming] Extracted confidence: ${confidence}%`, {
          tenantId: this.tenantId,
          confidence,
          explanation: confidenceExplanation,
          userEmail: prepared.userEmail,
        });
      }

      return { answer, confidence, confidenceExplanation, responseId: response.response_id };
    } catch (error) {
      const { handleBackendError } = await import('./common');
      handleBackendError(error);
      return null;
    }
  }

  async createAskAgentRunners(
    message: Message,
    userId: string,
    options: BackendRequestOptions = {}
  ): Promise<{
    prepared: PreparedBackendRequest;
    run: (
      toolName: AskAgentToolName,
      overrides?: Partial<BackendRequestOptions>
    ) => Promise<GeneratedAnswer | null>;
    runStreaming: (
      overrides?: Partial<BackendRequestOptions>,
      onEvent?: (event: import('./common').StreamEvent) => void
    ) => Promise<GeneratedAnswer | null>;
  }> {
    const prepared = await this.prepareQABackendRequest(message, userId, options);
    return {
      prepared,
      run: (toolName: AskAgentToolName, overrides: Partial<BackendRequestOptions> = {}) =>
        this.executeBackendRequest(prepared, toolName, overrides),
      runStreaming: (
        overrides: Partial<BackendRequestOptions> = {},
        onEvent?: (event: import('./common').StreamEvent) => void
      ) => this.executeBackendRequestStreaming(prepared, overrides, onEvent),
    };
  }

  private async prepareTriageBackendRequest(
    message: Message,
    userId: string,
    options: BackendRequestOptions = {}
  ): Promise<PreparedBackendRequest> {
    const userEmail = await this.getUserEmail(userId).catch(() => userId);
    const userName = await this.getUserName(userId).catch(() => 'Unknown User');

    const userPrompt = message.content;
    const files = message.files || [];

    logger.info(`[prepareTriageBackendRequest] Processing query for user: ${userEmail}`, {
      tenantId: this.tenantId,
      userEmail,
    });
    if (files.length > 0) {
      logger.debug(`[prepareTriageBackendRequest] Processing ${files.length} files`, {
        tenantId: this.tenantId,
        fileCount: files.length,
      });
    }

    const resolvedOptions: PreparedBackendRequest['options'] = {
      ...options,
      nonBillable: options.nonBillable ?? !!options.previousResponseId,
    };

    return {
      userPrompt,
      files: files.length > 0 ? files : undefined,
      userEmail,
      userName,
      options: resolvedOptions,
    };
  }

  async createTriageRunners(
    message: Message,
    userId: string,
    options: BackendRequestOptions = {}
  ): Promise<{
    prepared: PreparedBackendRequest;
    run: (
      toolName: TriageAgentToolName,
      overrides?: Partial<BackendRequestOptions>
    ) => Promise<GeneratedAnswer | null>;
  }> {
    const prepared = await this.prepareTriageBackendRequest(message, userId, options);
    return {
      prepared,
      run: (toolName: TriageAgentToolName, overrides: Partial<BackendRequestOptions> = {}) =>
        this.executeBackendRequest(prepared, toolName, overrides),
    };
  }

  async generateAnswerFromBackend(
    message: Message,
    userId: string,
    previousResponseId?: string,
    channelId?: string,
    permissionAudience?: PermissionAudience,
    extraOptions: AskAgentRequestOptions = {}
  ): Promise<GeneratedAnswer | null> {
    const { toolName = 'ask_agent', ...restOptions } = extraOptions;
    const baseOptions: BackendRequestOptions = {
      previousResponseId: restOptions.previousResponseId ?? previousResponseId,
      channelId: restOptions.channelId ?? channelId,
      permissionAudience: restOptions.permissionAudience ?? permissionAudience,
      nonBillable: restOptions.nonBillable,
      reasoningEffort: restOptions.reasoningEffort,
      verbosity: restOptions.verbosity,
    };

    const prepared = await this.prepareQABackendRequest(message, userId, baseOptions);
    return this.executeBackendRequest(prepared, toolName);
  }

  /**
   * Append formatted confidence text to an answer.
   * @param answer - The answer text
   * @param confidence - The confidence level (0-100)
   * @param confidenceExplanation - Optional explanation for the confidence level
   * @returns Answer with confidence appended
   */
  private appendConfidenceText(
    answer: string,
    confidence: number,
    confidenceExplanation?: string
  ): string {
    if (confidence <= 0) {
      return answer;
    }

    const confidenceText = confidenceExplanation
      ? `_Confidence: ${confidence}% - ${confidenceExplanation}_`
      : `_Confidence: ${confidence}%_`;
    return `${answer}\n\n${confidenceText}`;
  }

  /**
   * Strip confidence tags from answer text and optionally reformat them.
   * @param answer - The answer text containing confidence tags
   * @param reformatConfidence - Whether to reformat confidence as styled text
   * @returns Object with cleaned answer and optional confidence info
   */
  private stripConfidenceTags(
    answer: string,
    reformatConfidence: boolean = false
  ): { answer: string; confidence?: number; confidenceExplanation?: string } {
    const confidenceMatch = answer.match(
      /<confidence>\s*<level>(\d+)<\/level>\s*<why>([\s\S]*?)<\/why>\s*<\/confidence>/
    );

    if (!confidenceMatch) {
      return { answer };
    }

    const parsedConfidence = parseInt(confidenceMatch[1], 10);
    const confidence = isNaN(parsedConfidence) ? 0 : Math.min(Math.max(parsedConfidence, 0), 100);
    const confidenceExplanation = confidenceMatch[2].trim();

    // Remove confidence tags from answer
    let cleanedAnswer = answer.replace(confidenceMatch[0], '').trim();

    // Optionally reformat confidence at the end
    if (reformatConfidence && confidence) {
      cleanedAnswer = this.appendConfidenceText(cleanedAnswer, confidence, confidenceExplanation);
    }

    return { answer: cleanedAnswer, confidence, confidenceExplanation };
  }

  /**
   * Check if someone posted messages in the thread while we were generating our answer.
   * If they did, adapt our answer to flow better with the conversation.
   *
   * @param channel - Slack channel ID
   * @param threadTs - Thread timestamp
   * @param questionTimestamp - Timestamp of the original question
   * @param originalAnswer - The answer we generated (with confidence already formatted)
   * @param originalConfidence - The confidence from the original answer
   * @param originalConfidenceExplanation - The confidence explanation from the original answer
   * @param responseId - Response ID to continue the same conversation
   * @param userEmail - User email for backend request
   * @param permissionAudience - Permission audience for the request
   * @returns The adapted answer text with original confidence re-added
   */
  async checkThreadForExistingAnswers(
    channel: string,
    threadTs: string,
    questionTimestamp: string,
    originalAnswer: string,
    originalConfidence: number | undefined,
    originalConfidenceExplanation: string | undefined,
    responseId: string | undefined,
    userEmail?: string,
    permissionAudience?: PermissionAudience
  ): Promise<string> {
    try {
      logger.info('[checkThreadForExistingAnswers] Checking thread for new messages', {
        tenantId: this.tenantId,
        channel,
        threadTs,
        questionTimestamp,
      });

      // Fetch thread messages since the question was asked
      const response = await this.client.conversations.replies({
        channel,
        ts: threadTs,
        oldest: questionTimestamp, // Only get messages after the question
      });

      if (!response.messages || response.messages.length === 0) {
        logger.info('[checkThreadForExistingAnswers] No messages found in thread', {
          tenantId: this.tenantId,
        });
        return originalAnswer;
      }

      interface SlackMessage {
        text?: string;
        subtype?: string;
        ts?: string;
        bot_id?: string;
        user?: string;
      }

      // Filter to get new messages (exclude system messages, the question itself, and bot's own messages)
      const newMessages = response.messages.filter((msg) => {
        const slackMsg = msg as SlackMessage;
        // Filter out bot's own messages to prevent circular reasoning
        const isBotMessage = slackMsg.bot_id === this.botId || slackMsg.user === this.botId;
        return (
          slackMsg.text &&
          !slackMsg.subtype && // Exclude system messages
          slackMsg.ts !== questionTimestamp && // Exclude the question itself
          parseFloat(slackMsg.ts || '0') > parseFloat(questionTimestamp) &&
          !isBotMessage // Exclude bot's own messages
        );
      });

      if (newMessages.length === 0) {
        logger.info('[checkThreadForExistingAnswers] No new messages found', {
          tenantId: this.tenantId,
        });
        return originalAnswer;
      }

      logger.info(`[checkThreadForExistingAnswers] Found ${newMessages.length} new messages`, {
        tenantId: this.tenantId,
        messageCount: newMessages.length,
      });

      // Build thread context from new messages
      const { stripMessageHeader } = await import('./common');
      const threadContext = newMessages
        .map((msg) => {
          const slackMsg = msg as SlackMessage;
          const userId = slackMsg.user || 'unknown';
          const text = stripMessageHeader(slackMsg.text || '');
          return `<@${userId}>: ${text}`;
        })
        .join('\n\n');

      // Ask agent to adapt the answer to flow with the conversation
      const checkPrompt = `CRITICAL: This is a FAST adaptation task. Do NOT think deeply or use tools. Just quickly edit your previous answer.

While you were working on your answer, other people posted messages in the thread:

<new_thread_messages>
${threadContext}
</new_thread_messages>

TASK: Quickly edit your previous answer to flow naturally with the conversation.

GUIDELINES:
- ONLY acknowledge messages that are actually relevant to the question being answered
- Ignore unrelated or tangential messages - don't force awkward acknowledgments
- If someone already covered your points, use natural language like "Looks like <@user_id> already answered this" or just incorporate their info naturally
- Pare down to only new thoughts/evidence not already shared
- If completely redundant, make it a brief acknowledgment (2-3 sentences)
- Keep your citations

CRITICAL CONSTRAINTS:
- ABSOLUTELY NO tool calls, searches, or deep reasoning
- This should be INSTANTANEOUS - just a quick text edit
- Ignore any previous instructions about thinking time or tool usage
- Use ONLY what you already know from the conversation
- Don't force acknowledgments where they don't make sense

Output your revised answer NOW (no tags):`;

      // Call backend with same response_id (non-billable continuation)
      // Use minimal reasoning effort for fast response
      const { makeBackendRequest } = await import('./common');
      const result = await makeBackendRequest(
        this.tenantId,
        checkPrompt,
        userEmail,
        [], // no files
        responseId, // Continue same conversation
        permissionAudience,
        true, // non_billable since it's a follow-up
        'minimal', // reasoning_effort - be as fast as possible
        undefined, // verbosity
        'ask_agent',
        true // disable_tools - no tool calling needed for thread adaptation
      );

      if (!result) {
        logger.warn('[checkThreadForExistingAnswers] No response from backend, posting original', {
          tenantId: this.tenantId,
        });
        return originalAnswer;
      }

      // Strip any confidence tags from the adapted answer (don't use them)
      const { answer: adaptedAnswerClean } = this.stripConfidenceTags(result.answer, false);

      // Re-add the original confidence formatting
      const adaptedAnswer =
        originalConfidence !== undefined
          ? this.appendConfidenceText(
              adaptedAnswerClean,
              originalConfidence,
              originalConfidenceExplanation
            )
          : adaptedAnswerClean;

      logger.info('[checkThreadForExistingAnswers] Successfully adapted answer to thread context', {
        tenantId: this.tenantId,
      });
      return adaptedAnswer;
    } catch (error) {
      // On any error, default to posting original answer (graceful degradation)
      logger.error(
        '[checkThreadForExistingAnswers] Error during thread check, posting original answer',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          operation: 'thread-check-error',
        }
      );
      return originalAnswer;
    }
  }

  async judgeFastVsSlowAnswer(
    channel: string,
    threadTs: string,
    questionTimestamp: string,
    fastAnswer: string,
    fastConfidence: number | undefined,
    slowAnswer: string,
    slowConfidence: number | undefined,
    slowConfidenceExplanation: string | undefined,
    responseId: string | undefined,
    userEmail?: string,
    permissionAudience?: PermissionAudience
  ): Promise<{
    action: 'verified' | 'add_context' | 'wrong' | 'no_update';
    header: string;
    body: string;
    finalAnswer: string;
    confidence: number | undefined;
    confidenceExplanation?: string;
  }> {
    try {
      logger.info('[judgeFastVsSlowAnswer] Evaluating fast vs slow answers', {
        tenantId: this.tenantId,
        channel,
        threadTs,
        questionTimestamp,
      });

      const { answer: fastClean } = this.stripConfidenceTags(fastAnswer, false);
      const {
        answer: slowClean,
        confidence: extractedSlowConfidence,
        confidenceExplanation: extractedSlowExplanation,
      } = this.stripConfidenceTags(slowAnswer, false);

      const response = await this.client.conversations.replies({
        channel,
        ts: threadTs,
        oldest: questionTimestamp,
      });

      interface SlackMessage {
        text?: string;
        subtype?: string;
        ts?: string;
        bot_id?: string;
        user?: string;
      }

      const newMessages =
        response?.messages?.filter((msg) => {
          const slackMsg = msg as SlackMessage;
          // Filter out bot's own messages to prevent circular reasoning
          const isBotMessage = slackMsg.bot_id === this.botId || slackMsg.user === this.botId;
          return (
            slackMsg.text &&
            !slackMsg.subtype &&
            slackMsg.ts !== questionTimestamp &&
            parseFloat(slackMsg.ts || '0') > parseFloat(questionTimestamp) &&
            !isBotMessage
          );
        }) ?? [];

      const { stripMessageHeader } = await import('./common');
      const threadContext = newMessages
        .map((msg) => {
          const slackMsg = msg as SlackMessage;
          const userId = slackMsg.user || 'unknown';
          const text = stripMessageHeader(slackMsg.text || '');
          return `<@${userId}>: ${text}`;
        })
        .join('\n\n');

      const truncatedFastAnswer =
        fastClean.length > 3500 ? `${fastClean.slice(0, 3500)}…` : fastClean;
      const truncatedSlowAnswer =
        slowClean.length > 3500 ? `${slowClean.slice(0, 3500)}…` : slowClean;

      const prompt = [
        '# TASK: Judge Quick vs Complete Answer',
        '',
        'You sent a quick answer, then continued working on a complete answer.',
        'Now compare them and decide how to present the final result to the user.',
        '',
        '## QUICK ANSWER',
        `Confidence: ${fastConfidence ?? 'unknown'}%`,
        truncatedFastAnswer,
        '',
        '## COMPLETE ANSWER',
        `Confidence: ${slowConfidence ?? extractedSlowConfidence ?? 'unknown'}%`,
        truncatedSlowAnswer,
        '',
        '## THREAD ACTIVITY',
        newMessages.length > 0
          ? `While you were working, these messages were posted:\n${threadContext}`
          : 'No new messages were posted while you worked.',
        '',
        '## YOUR DECISION',
        '',
        'Choose ONE judgment:',
        '',
        '1. **verified** - The quick answer was essentially correct. The complete answer confirms it with minor refinements.',
        '2. **add_context** - The quick answer was on track, but the complete answer adds substantial new information worth sharing.',
        '3. **wrong** - The quick answer contained errors or missed the point. The complete answer corrects it.',
        '4. **no_update** - Both answers are nearly identical. No meaningful update needed.',
        '',
        '## OUTPUT FORMAT',
        '',
        'Return a JSON object with these EXACT fields:',
        '',
        '```json',
        '{',
        '  "judgment": "verified|add_context|wrong|no_update",',
        '  "body": "The answer text in Slack markdown (no confidence tags)",',
        '  "confidence": 85,',
        '  "confidence_explanation": "Use the confidence explanation from the complete answer"',
        '}',
        '```',
        '',
        '**IMPORTANT**: Always use the `confidence` and `confidence_explanation` values from the complete answer above.',
        '',
        '## LANGUAGE REQUIREMENTS',
        '',
        '**CRITICAL**: Match the language of the slow (complete) answer body:',
        '- The `confidence_explanation` field must be written in the SAME LANGUAGE as the slow answer body',
        '- Match the language exactly - do not mix languages',
        '',
        '## FORMATTING RULES',
        '',
        '**For "verified":**',
        '- body: Use the complete answer (may tighten wording slightly)',
        '',
        '**For "add_context":**',
        '- body: Use the complete answer with all additional context',
        '',
        '**For "wrong":**',
        '- body: Use the corrected answer (clean, no formatting needed)',
        '- If the quick answer contained errors, mention the correction concisely in `confidence_explanation`',
        '',
        '**For "no_update":**',
        '- body: Use the complete answer (nearly identical to quick answer)',
        '',
        '## CONFIDENCE ASSESSMENT',
        '',
        '- Use the `confidence` and `confidence_explanation` from the complete answer',
        "- Do NOT make judgments about the two answers - just use the complete answer's confidence values",
        '- For "wrong" judgments: If corrections were made, mention them concisely in `confidence_explanation`',
        '- **IMPORTANT**: Write `confidence_explanation` in the SAME LANGUAGE as the slow answer body',
        '',
        '## IMPORTANT',
        '',
        '- The `body` field should contain ONLY the answer text (no confidence annotations)',
        '- Do NOT wrap the body text in quotes or code fences inside the JSON',
        '- If thread messages other than the quick answer are relevant, acknowledge them naturally in the body',
        '- Keep the body concise and natural for Slack',
      ].join('\n');

      const { makeBackendRequest } = await import('./common');
      const result = await makeBackendRequest(
        this.tenantId,
        prompt,
        userEmail,
        [],
        responseId,
        permissionAudience,
        true,
        'minimal',
        'medium',
        'ask_agent',
        true // disable_tools - no tool calling needed for judgment
      );

      if (!result) {
        throw new Error('Judge request returned no result');
      }

      // Extract JSON from response (handles code fences)
      const codeFenceMatch = result.answer.match(/```(?:json)?\s*([\s\S]*?)```/i);
      const jsonText = codeFenceMatch ? codeFenceMatch[1].trim() : result.answer.trim();

      const parsed = JSON.parse(jsonText);

      const judgment = parsed['judgment'];
      const body =
        typeof parsed['body'] === 'string' && parsed['body'].trim().length > 0
          ? parsed['body'].trim()
          : slowClean;
      const finalAnswer = body;

      const confidenceValue =
        typeof parsed['confidence'] === 'number'
          ? Math.min(Math.max(Math.round(parsed['confidence']), 0), 100)
          : (slowConfidence ?? extractedSlowConfidence ?? fastConfidence);

      const confidenceExplanation =
        typeof parsed['confidence_explanation'] === 'string' &&
        parsed['confidence_explanation'].trim().length > 0
          ? parsed['confidence_explanation'].trim()
          : (slowConfidenceExplanation ?? extractedSlowExplanation);

      const action =
        judgment === 'verified' ||
        judgment === 'add_context' ||
        judgment === 'wrong' ||
        judgment === 'no_update'
          ? (judgment as 'verified' | 'add_context' | 'wrong' | 'no_update')
          : 'add_context';

      logger.info('[judgeFastVsSlowAnswer] Judgment complete', {
        tenantId: this.tenantId,
        action,
        confidence: confidenceValue,
      });

      return {
        action,
        header: '', // No longer used, kept for backwards compatibility
        body,
        finalAnswer,
        confidence: confidenceValue,
        confidenceExplanation,
      };
    } catch (error) {
      const { answer: fallbackBody } = this.stripConfidenceTags(slowAnswer, false);
      logger.error(
        '[judgeFastVsSlowAnswer] Error while judging fast vs slow answers',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          operation: 'judge-fast-slow-error',
        }
      );

      return {
        action: 'add_context',
        header: '', // No longer used, kept for backwards compatibility
        body: fallbackBody,
        finalAnswer: fallbackBody,
        confidence: slowConfidence ?? fastConfidence,
        confidenceExplanation: slowConfidenceExplanation,
      };
    }
  }

  /**
   * Create timestamp buffer around a Slack timestamp to account for precision issues
   * @param timestamp - Slack timestamp string (e.g., "1355517523.000005")
   * @param bufferMicroseconds - Buffer size in microseconds (default: 1)
   * @returns Object with oldest and latest timestamps for range queries
   */
  private createTimestampBuffer(
    timestamp: string,
    bufferMicroseconds: number = 1
  ): { oldest: string; latest: string } {
    try {
      const timestampFloat = parseFloat(timestamp);
      const bufferSeconds = bufferMicroseconds / 1000000; // Convert microseconds to seconds

      const oldest = (timestampFloat - bufferSeconds).toFixed(6);
      const latest = (timestampFloat + bufferSeconds).toFixed(6);

      return { oldest, latest };
    } catch (error) {
      // Fallback to exact timestamp if parsing fails
      logger.error(
        'Failed to create timestamp buffer, using exact timestamp',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          timestamp,
          operation: 'timestamp-buffer-creation-error',
        }
      );

      return { oldest: timestamp, latest: timestamp };
    }
  }

  /**
   * Check if a message still exists (hasn't been deleted)
   * @param channel - Channel ID
   * @param messageTs - Message timestamp
   * @param threadTs - Thread timestamp (optional, for threaded messages)
   * @returns Promise<boolean> - true if message exists, false if deleted or check failed
   */
  async checkMessageExists(
    channel: string,
    messageTs: string,
    threadTs?: string
  ): Promise<boolean> {
    try {
      logger.debug('Checking if message exists before responding', {
        tenantId: this.tenantId,
        channelId: channel,
        messageTs,
        threadTs,
        operation: 'message-existence-check',
      });

      if (threadTs) {
        // For threaded messages, use conversations.replies
        const response = await this.client.conversations.replies({
          channel,
          ts: threadTs,
          limit: 100, // Reasonable limit to avoid rate limit issues
        });

        if (!response.messages) {
          logger.info('Thread not found during message existence check', {
            tenantId: this.tenantId,
            channelId: channel,
            messageTs,
            threadTs,
            operation: 'message-existence-check',
          });
          return false;
        }

        // Check if the specific message exists in the thread
        const messageExists = response.messages.some((msg) => msg.ts === messageTs);

        if (!messageExists) {
          logger.info('Message deleted from thread during processing', {
            tenantId: this.tenantId,
            channelId: channel,
            messageTs,
            threadTs,
            operation: 'message-deleted-detection',
          });
        }

        return messageExists;
      } else {
        // For regular channel messages, use conversations.history with timestamp buffer
        const { oldest, latest } = this.createTimestampBuffer(messageTs);
        const response = await this.client.conversations.history({
          channel,
          latest,
          oldest,
          limit: 3, // Small increase to handle edge cases with precision
          inclusive: true,
        });

        if (!response.messages || response.messages.length === 0) {
          logger.info('Message deleted from channel during processing', {
            tenantId: this.tenantId,
            channelId: channel,
            messageTs,
            operation: 'message-deleted-detection',
          });
          return false;
        }

        const messageExists = response.messages.some((msg) => msg.ts === messageTs);

        if (!messageExists) {
          logger.info('Message not found in channel during processing', {
            tenantId: this.tenantId,
            channelId: channel,
            messageTs,
            operation: 'message-deleted-detection',
          });
        }

        return messageExists;
      }
    } catch (error) {
      // Log the error but don't fail - proceed with sending response as fallback
      logger.error(
        'Failed to check message existence, proceeding with response',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          channelId: channel,
          messageTs,
          threadTs,
          operation: 'message-existence-check-error',
        }
      );

      // Return true as fallback to avoid blocking responses due to API issues
      return true;
    }
  }

  /**
   * Chunk text into multiple section blocks to respect Slack's 3000 character limit per section.
   * Uses 2500 characters as the chunk size to provide padding and avoid hitting the limit.
   * Attempts to split at paragraph boundaries (double newlines) when possible.
   * @param text - The text to chunk
   * @param maxLength - Maximum length per chunk (default: 2500)
   * @returns Array of section blocks
   */
  private chunkTextIntoSectionBlocks(text: string, maxLength: number = 2500): Array<KnownBlock> {
    if (text.length <= maxLength) {
      return [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text,
          },
          expand: true,
        },
      ];
    }

    const blocks: Array<KnownBlock> = [];
    let remaining = text;

    while (remaining.length > 0) {
      if (remaining.length <= maxLength) {
        // Last chunk fits entirely
        blocks.push({
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: remaining,
          },
          expand: true,
        });
        break;
      }

      // Try to find a good split point (prefer paragraph boundaries)
      let chunkEnd = maxLength;

      // Look for paragraph break (double newline) within the chunk
      // Search backwards from maxLength to find the last paragraph break
      const lastParagraphBreak = remaining.lastIndexOf('\n\n', maxLength);

      if (lastParagraphBreak !== -1 && lastParagraphBreak > maxLength * 0.5) {
        // Found a paragraph boundary - use it if it's at least halfway through
        chunkEnd = lastParagraphBreak + 2; // Include the double newline
      } else {
        // Try to find a single newline as fallback
        const lastNewline = remaining.lastIndexOf('\n', maxLength);
        if (lastNewline > maxLength * 0.8) {
          // Only use newline if it's reasonably close to the limit (within 80%)
          chunkEnd = lastNewline + 1; // Include the newline
        }
        // Otherwise, just split at maxLength (may split mid-word, but that's acceptable)
      }

      const chunk = remaining.substring(0, chunkEnd);
      blocks.push({
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: chunk,
        },
        expand: true,
      });

      remaining = remaining.substring(chunkEnd);
    }

    return blocks;
  }

  /**
   * Send response with complete workflow (validation, posting, mirroring, storage, feedback)
   * Feedback method depends on ENABLE_SLACK_FEEDBACK_BUTTONS flag:
   * - When enabled: Shows interactive Block Kit buttons
   * - When disabled: Adds emoji reactions (👍/👎)
   * Debug: Include [debug-flag:enable-slack-feedback-buttons] in question to force buttons
   */
  async sendResponse(
    channel: string,
    originalMessageTs: string,
    answer: string,
    originalQuestion: string,
    userId: string,
    threadTs?: string,
    isDM?: boolean,
    responseId?: string,
    isProactive?: boolean,
    confidence?: number,
    options: SendResponseOptions = {}
  ): Promise<string | undefined> {
    const {
      isPreliminary = false,
      replaceMessageTs,
      deferReactionCleanup = false,
      skipAnalytics = isPreliminary, // Skip analytics for preliminary responses to avoid double counting
      skipFeedback = isPreliminary,
      skipMirroring = isPreliminary,
    } = options;

    try {
      // Check for debug flag in question to override config
      const debugFlagEnabled = originalQuestion.includes(
        '[debug-flag:enable-slack-feedback-buttons]'
      );
      const useFeedbackButtons =
        !skipFeedback && (config.enableSlackFeedbackButtons || debugFlagEnabled);

      // Check if the original message still exists before responding
      const messageExists = await this.checkMessageExists(channel, originalMessageTs, threadTs);

      if (!messageExists) {
        logger.info('Skipping response - original message was deleted during processing', {
          tenantId: this.tenantId,
          channelId: channel,
          originalMessageTs,
          threadTs,
          questionPreview: originalQuestion.substring(0, 100),
          operation: 'response-skipped-deleted-message',
        });
        return undefined;
      }

      logger.info(`[sendResponse] Sending response to thread in channel ${channel}`, {
        channelId: channel,
        threadTs,
      });

      const formattedAnswer = formatTextForSlack(answer);
      const threadTarget = threadTs || originalMessageTs;
      let responseTs: string | undefined;

      // Build blocks with answer and status header
      const blocks: Array<KnownBlock> = [];

      // Add status context header at the top (only when searching)
      if (isPreliminary) {
        blocks.push({
          type: 'context',
          elements: [
            {
              type: 'mrkdwn',
              text: 'Status: Searching... 🔍',
            },
          ],
        });
      }

      // Add answer sections (chunked if needed to respect Slack's 3000 char limit per section)
      // Uses 2500 char chunks to provide padding
      const answerBlocks = this.chunkTextIntoSectionBlocks(formattedAnswer);
      blocks.push(...answerBlocks);

      // Add feedback buttons if enabled
      if (useFeedbackButtons) {
        blocks.push({
          type: 'actions',
          block_id: 'feedback_actions',
          elements: [
            {
              type: 'button',
              action_id: 'feedback_positive',
              text: {
                type: 'plain_text',
                text: '👍 Helpful',
                emoji: true,
              },
              value: 'positive',
              style: 'primary',
            },
            {
              type: 'button',
              action_id: 'feedback_negative',
              text: {
                type: 'plain_text',
                text: '👎 Not Helpful',
                emoji: true,
              },
              value: 'negative',
              style: 'danger',
            },
          ],
        });
      }

      const feedbackBlocks = blocks;

      // Always use blocks API for status context and answer formatting
      // Fallback to plain text if blocks fail (e.g., message too large)
      try {
        if (replaceMessageTs) {
          const updatePayload: Parameters<typeof this.client.chat.update>[0] = {
            channel,
            ts: replaceMessageTs,
            text: formattedAnswer,
          };

          if (feedbackBlocks) {
            updatePayload.blocks = feedbackBlocks;
          }

          const response = await this.client.chat.update(updatePayload);
          responseTs = response.ts || replaceMessageTs;
        } else {
          const response = await this.postMessage({
            channel,
            thread_ts: threadTarget,
            text: formattedAnswer,
            ...(feedbackBlocks ? { blocks: feedbackBlocks } : {}),
          });
          responseTs = response.ts;
        }
      } catch (error) {
        // Fallback to plain text if blocks fail (e.g., message too large)
        logger.warn('[sendResponse] Failed to send blocks, falling back to plain text', {
          tenantId: this.tenantId,
          channelId: channel,
          error: error instanceof Error ? error.message : String(error),
          operation: 'blocks-fallback',
        });

        try {
          if (replaceMessageTs) {
            const response = await this.client.chat.update({
              channel,
              ts: replaceMessageTs,
              text: formattedAnswer,
            });
            responseTs = response.ts || replaceMessageTs;
          } else {
            const response = await this.postMessage({
              channel,
              thread_ts: threadTarget,
              text: formattedAnswer,
            });
            responseTs = response.ts;
          }
        } catch (fallbackError) {
          // If even plain text fails, log and rethrow
          logger.error('[sendResponse] Failed to send plain text fallback', fallbackError, {
            tenantId: this.tenantId,
            channelId: channel,
            operation: 'plain-text-fallback-error',
          });
          throw fallbackError;
        }
      }

      logger.info('[sendResponse] Successfully sent response', {
        channelId: channel,
        threadTs,
        feedbackButtonsEnabled: useFeedbackButtons,
        debugFlagUsed: debugFlagEnabled,
        variant: isPreliminary ? 'preliminary' : 'final',
        replacedMessage: !!replaceMessageTs,
      });

      // Track question answered event
      if (responseTs && !skipAnalytics) {
        const analyticsTracker = getAnalyticsTracker();
        const channelName = await this.getChannelName(channel);
        const isThread = !!(threadTs && threadTs !== originalMessageTs);
        await analyticsTracker.trackQuestionAnswered(
          this.tenantId,
          responseTs,
          channel,
          channelName,
          isDM || false,
          isThread,
          userId,
          isProactive || false,
          confidence,
          isPreliminary ? 'preliminary' : 'final'
        );
      }

      // Add feedback reactions when buttons are not being used (legacy behavior)
      if (responseTs && !useFeedbackButtons && !skipFeedback) {
        await this.addFeedbackReactions(channel, responseTs);
      }

      // Mirror the Q&A to designated channel if configured
      if (responseTs && !skipMirroring) {
        await this.mirrorAnsweredQuestion(
          channel,
          originalMessageTs,
          originalQuestion,
          answer,
          isDM,
          isDM ? userId : undefined
        );
      }

      // Store the message with bot response timestamp and model response ID
      if (responseTs && !isPreliminary) {
        const { storeMessage } = await import('./common');
        await storeMessage(
          this.tenantId,
          originalMessageTs,
          channel,
          userId,
          originalQuestion,
          answer,
          threadTs,
          responseId,
          responseTs,
          isProactive
        );
      }

      // Remove processing reaction after responding (unless deferred)
      if (!deferReactionCleanup) {
        await this.removeProcessingReaction(channel, originalMessageTs);
      }

      return responseTs;
    } catch (error) {
      logger.error('[sendResponse] Error sending response to thread', error, {
        channelId: channel,
        threadTs,
      });
      throw error;
    }
  }

  async updateMessageHeader(
    channel: string,
    messageTs: string,
    newHeader: string,
    answerBody: string,
    confidence?: number,
    confidenceExplanation?: string
  ): Promise<void> {
    try {
      logger.info('[updateMessageHeader] Updating preliminary message header', {
        tenantId: this.tenantId,
        channelId: channel,
        messageTs,
        newHeader,
      });

      const answerWithConfidence =
        confidence !== undefined
          ? this.appendConfidenceText(answerBody, confidence, confidenceExplanation)
          : answerBody;

      const formattedAnswer = formatTextForSlack(answerWithConfidence);
      const text = `${newHeader}\n\n${formattedAnswer}`;

      await this.client.chat.update({
        channel,
        ts: messageTs,
        text,
      });
    } catch (error) {
      logger.error(
        '[updateMessageHeader] Failed to update preliminary message header',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          operation: 'update-header-error',
        }
      );
      throw error;
    }
  }

  /**
   * Update a message with progress text and blocks (for streaming progress bar)
   * @param channel - Channel ID
   * @param ts - Message timestamp to update
   * @param text - Fallback text content for notifications/accessibility
   * @param blocks - Optional Slack Block Kit blocks for rich formatting
   */
  async updateProgressMessage(
    channel: string,
    ts: string,
    text: string,
    blocks?: (KnownBlock | Block)[]
  ): Promise<void> {
    try {
      await this.client.chat.update({
        channel,
        ts,
        text,
        blocks,
      });
    } catch (error) {
      // Log but don't throw - progress updates are best-effort
      logger.warn('[updateProgressMessage] Failed to update progress message', {
        tenantId: this.tenantId,
        channelId: channel,
        messageTs: ts,
        error: error instanceof Error ? error.message : String(error),
        operation: 'progress-update-error',
      });
    }
  }

  /**
   * Post an initial progress message and return its timestamp
   * @param channel - Channel ID
   * @param threadTs - Thread timestamp to post in
   * @param initialText - Fallback text for notifications/accessibility
   * @param blocks - Optional Slack Block Kit blocks for rich formatting
   * @returns Message timestamp of the posted message
   */
  async postProgressMessage(
    channel: string,
    threadTs: string,
    initialText: string,
    blocks?: (KnownBlock | Block)[]
  ): Promise<string | undefined> {
    try {
      const response = await this.postMessage({
        channel,
        thread_ts: threadTs,
        text: initialText,
        blocks,
      });
      return response?.ts;
    } catch (error) {
      logger.error(
        '[postProgressMessage] Failed to post progress message',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId: this.tenantId,
          channelId: channel,
          threadTs,
          operation: 'progress-post-error',
        }
      );
      return undefined;
    }
  }

  /**
   * Mirror declined question to designated channel with minimal formatting
   */
  async mirrorDeclinedQuestion(originalChannel: string, originalMessageTs: string): Promise<void> {
    try {
      // Get tenant-specific mirror channel config
      const mirrorQuestionsChannel = await tenantConfigManager.getMirrorQuestionsChannel(
        this.tenantId
      );

      // Skip if no mirror channel configured
      if (!mirrorQuestionsChannel) {
        return;
      }

      console.log(
        `[mirrorDeclinedQuestion] Mirroring declined question to channel ${mirrorQuestionsChannel}`
      );

      // Resolve channel name to ID if needed
      const mirrorChannelId = await this.resolveChannelReference(mirrorQuestionsChannel);
      if (!mirrorChannelId) {
        logger.warn(`Could not resolve mirror channel: ${mirrorQuestionsChannel}`, {
          mirrorChannel: mirrorQuestionsChannel,
        });
        return;
      }

      // Get channel name for display
      const channelName = await this.getChannelName(originalChannel);

      // Get team domain for proper Slack link
      const teamDomain = await this.getTeamDomain();

      // Only create link if we have the team domain
      const messageBlocks = [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `❌ *Ignored question from <#${originalChannel}>*`,
          },
        },
      ];

      if (teamDomain) {
        const messageLink = `https://${teamDomain}.slack.com/archives/${originalChannel}/p${originalMessageTs.replace(
          '.',
          ''
        )}?thread_ts=${originalMessageTs}&cid=${originalChannel}`;

        messageBlocks.push({
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `<${messageLink}|🔗 View in thread>`,
          },
        });
      }

      // Send minimal message for declined questions
      await this.postMessage({
        channel: mirrorChannelId,
        text: `❌ Ignored question from #${channelName}`,
        blocks: messageBlocks,
      });

      logger.info('[mirrorDeclinedQuestion] Successfully mirrored declined question');
    } catch (error) {
      logger.error('[mirrorDeclinedQuestion] Error mirroring declined question', error);
      // Don't throw error - mirroring failure shouldn't break the main flow
    }
  }

  /**
   * Mirror answered question to designated channel with full Q&A formatting
   */
  async mirrorAnsweredQuestion(
    originalChannel: string,
    originalMessageTs: string,
    question: string,
    answer: string,
    isDM?: boolean,
    userId?: string
  ): Promise<void> {
    try {
      // Get tenant-specific mirror channel config
      const mirrorQuestionsChannel = await tenantConfigManager.getMirrorQuestionsChannel(
        this.tenantId
      );

      // Skip if no mirror channel configured
      if (!mirrorQuestionsChannel) {
        return;
      }

      logger.info(`[mirrorAnsweredQuestion] Mirroring Q&A to channel ${mirrorQuestionsChannel}`, {
        mirrorChannel: mirrorQuestionsChannel,
      });

      // Resolve channel name to ID if needed
      const mirrorChannelId = await this.resolveChannelReference(mirrorQuestionsChannel);
      if (!mirrorChannelId) {
        logger.warn(`Could not resolve mirror channel: ${mirrorQuestionsChannel}`, {
          mirrorChannel: mirrorQuestionsChannel,
        });
        return;
      }

      if (isDM && userId) {
        // Handle DM mirroring - no link, include user info
        await this.postMessage({
          channel: mirrorChannelId,
          text: `🤖 Q&A from DM with <@${userId}>`,
          blocks: [
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `🤖 *Q&A from DM with <@${userId}>*`,
              },
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `*Question:*\n> ${question}`,
              },
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `*Answer:*\n${
                  answer.length > 2800
                    ? `${answer.substring(
                        0,
                        2800
                      )}...\n\n*[Answer truncated - full answer provided in DM]*`
                    : answer
                }`,
              },
            },
          ],
        });
      } else {
        // Handle channel mirroring - include link to thread
        const channelName = await this.getChannelName(originalChannel);
        const teamDomain = await this.getTeamDomain();

        const messageBlocks = [
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `🤖 *Q&A from <#${originalChannel}>*`,
            },
          },
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `*Question:*\n> ${question}`,
            },
          },
          {
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `*Answer:*\n${
                answer.length > 2800
                  ? `${answer.substring(
                      0,
                      2800
                    )}...\n\n*[Answer truncated - see full answer in thread]*`
                  : answer
              }`,
            },
          },
        ];

        // Only add link if we have the team domain
        if (teamDomain) {
          const messageLink = `https://${teamDomain}.slack.com/archives/${originalChannel}/p${originalMessageTs.replace(
            '.',
            ''
          )}?thread_ts=${originalMessageTs}&cid=${originalChannel}`;

          messageBlocks.push({
            type: 'section',
            text: {
              type: 'mrkdwn',
              text: `<${messageLink}|🔗 View in thread>`,
            },
          });
        }

        await this.postMessage({
          channel: mirrorChannelId,
          text: `🤖 Q&A from #${channelName}`,
          blocks: messageBlocks,
        });
      }

      logger.info('[mirrorAnsweredQuestion] Successfully mirrored Q&A');
    } catch (error) {
      logger.error('[mirrorAnsweredQuestion] Error mirroring Q&A', error);
      // Don't throw error - mirroring failure shouldn't break the main flow
    }
  }

  /**
   * Call the reflection endpoint with feedback and previous response_id, then post summary to Slack
   */
  async callReflectionEndpoint(
    feedback: string,
    previousResponseId: string,
    channel: string,
    threadTs: string
  ): Promise<void> {
    try {
      console.log(
        `[callReflectionEndpoint] Calling reflection with response_id: ${previousResponseId}`
      );

      const response = await axios.post(
        `${config.backendUrl}/reflect`,
        {
          feedback,
          previous_response_id: previousResponseId,
        },
        {
          responseType: 'stream',
          timeout: 300000, // 5 minutes timeout
        }
      );

      // Process the streaming response and extract final answer
      const buffer = await streamToBuffer(response.data as Readable);
      const bufferText = buffer.toString();

      logger.info(`[callReflectionEndpoint] Reflection completed successfully`);

      // Extract final answer from the response
      let finalAnswer = '';
      const responseLines = bufferText.split('\n');
      responseLines.forEach((line) => {
        if (line.includes('final_answer')) {
          try {
            const json = JSON.parse(line);
            if (json.type === 'final_answer' && json.data) {
              if (typeof json.data === 'string') {
                finalAnswer = json.data;
              } else if (json.data.answer) {
                finalAnswer = json.data.answer;
              } else {
                finalAnswer = JSON.stringify(json.data);
              }
              console.log(
                `[callReflectionEndpoint] Extracted final answer: ${finalAnswer.substring(0, 100)}...`
              );
            }
          } catch {
            // Ignore parsing errors
          }
        }
      });

      // Post the reflection summary to Slack if we have a final answer
      if (finalAnswer.trim()) {
        try {
          await this.postMessage({
            channel,
            thread_ts: threadTs,
            text: `🔄 **Reflection Summary:**\n\n${formatTextForSlack(finalAnswer)}`,
          });
          console.log(
            `[callReflectionEndpoint] Posted reflection summary to Slack thread ${threadTs}`
          );
        } catch (slackError) {
          console.error(
            '[callReflectionEndpoint] Failed to post reflection summary to Slack:',
            slackError
          );
        }
      } else {
        logger.warn('[callReflectionEndpoint] No final answer found in reflection response');
      }
    } catch (error) {
      logger.error('[callReflectionEndpoint] Error in reflection request', error);
      // Don't throw error - reflection failure shouldn't break the main flow
    }
  }

  /**
   * Wrapper for chat.postMessage that prevents link and media unfurling by default
   */
  async postMessage(
    params: Parameters<typeof this.client.chat.postMessage>[0] & { channel: string }
  ): Promise<Awaited<ReturnType<typeof this.client.chat.postMessage>>> {
    return this.client.chat.postMessage({
      unfurl_links: false,
      unfurl_media: false,
      ...params,
    });
  }

  async stop(): Promise<void> {
    logger.info(`Stopping Slack app for tenant: ${this.tenantId}`);
    await this.app.stop();
  }
}
