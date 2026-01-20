// API client for stats endpoints
import { apiClient } from './client';
export interface SlackReaction {
  message_id: string;
  channel_id: string;
  user_id: string;
  reaction: string;
  created_at: string;
}

export interface SlackFeedback {
  message_id: string;
  channel_id: string;
  user_id: string;
  feedback_type: 'positive' | 'negative';
  created_at: string;
}

export interface ThreadStat {
  message_id: string;
  channel_id: string;
  user_id: string;
  question: string;
  answer: string;
  created_at: string;
  is_proactive: boolean;
  channel_name?: string;
  user_name?: string;
  user_display_name?: string;
  reactions: SlackReaction[];
  button_feedback: SlackFeedback[];
}

export interface ThreadMessage {
  message_id: string;
  channel_id: string;
  user_id: string;
  text: string;
  timestamp: string;
  thread_ts?: string;
  is_bot: boolean;
  user_name?: string;
  user_display_name?: string;
  reactions: SlackReaction[];
}

export interface ThreadDetails {
  original_question_message_id: string;
  bot_response_message_id: string;
  channel_id: string;
  thread_ts: string;
  messages: ThreadMessage[];
}

export interface ThreadStatsResponse {
  threads: ThreadStat[];
  total: number;
  hasMore: boolean;
}

export interface StatsSummary {
  totalMessages: number;
  channelMessages: number;
  dmMessages: number;
  messagesWithReactions: number;
  messagesWithPositiveReactions: number;
  messagesWithNegativeReactions: number;
  totalReactions: number;
  positiveReactions: number;
  negativeReactions: number;
  messagesWithButtonFeedback: number;
  messagesWithPositiveFeedback: number;
  messagesWithNegativeFeedback: number;
  totalButtonFeedback: number;
  positiveButtonFeedback: number;
  negativeButtonFeedback: number;
  uniqueChannels: number;
  uniqueUsers: number;
}

export interface ThreadStatsFilters {
  page?: number;
  limit?: number;
  date_from?: string;
  date_to?: string;
}

export interface SummaryStatsFilters {
  date_from?: string;
  date_to?: string;
}

const API_BASE = '/api/stats';

export interface SourceStats {
  [source: string]: {
    indexed: number;
    discovered: {
      [entity: string]: number;
    };
  };
}

export const statsApi = {
  async getThreadStats(filters: ThreadStatsFilters = {}): Promise<ThreadStatsResponse> {
    const params = new URLSearchParams();

    if (filters.page) params.set('page', filters.page.toString());
    if (filters.limit) params.set('limit', filters.limit.toString());
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);

    const url = `${API_BASE}/threads${params.toString() ? `?${params.toString()}` : ''}`;

    return await apiClient.get<ThreadStatsResponse>(url);
  },

  async getThreadDetails(messageId: string): Promise<ThreadDetails> {
    const url = `${API_BASE}/threads/${messageId}/full`;
    return await apiClient.get<ThreadDetails>(url);
  },

  async getSummaryStats(filters: SummaryStatsFilters = {}): Promise<StatsSummary> {
    const params = new URLSearchParams();

    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);

    const url = `${API_BASE}/summary${params.toString() ? `?${params.toString()}` : ''}`;

    return await apiClient.get<StatsSummary>(url);
  },

  async getSourceStats(): Promise<SourceStats> {
    const url = `${API_BASE}/sources`;
    return await apiClient.get<SourceStats>(url);
  },
};
