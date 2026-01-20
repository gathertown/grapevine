import { apiClient } from './client';

export interface TemplateField {
  field_name: string;
  field_prompt: string;
}

export interface KnowledgeBaseConfig {
  context_gathering_prompt: string;
  template: TemplateField[];
}

export interface KnowledgeBase {
  id: string;
  name: string;
  config: KnowledgeBaseConfig;
  created_at: string;
  updated_at: string;
}

export interface Article {
  id: string;
  kb_id: string;
  title: string;
  content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ListKnowledgeBasesResponse {
  knowledge_bases: KnowledgeBase[];
}

export interface ListArticlesResponse {
  articles: Article[];
}

export const knowledgeBasesApi = {
  /**
   * List all knowledge bases
   */
  list: async (): Promise<ListKnowledgeBasesResponse> => {
    return apiClient.get<ListKnowledgeBasesResponse>('/api/knowledge-bases');
  },

  /**
   * Get a specific knowledge base
   */
  get: async (id: string): Promise<KnowledgeBase> => {
    return apiClient.get<KnowledgeBase>(`/api/knowledge-bases/${id}`);
  },

  /**
   * Create a new knowledge base
   */
  create: async (name: string, config: KnowledgeBaseConfig): Promise<KnowledgeBase> => {
    return apiClient.post<KnowledgeBase>('/api/knowledge-bases', { name, config });
  },

  /**
   * Update a knowledge base
   */
  update: async (
    id: string,
    data: { name?: string; config?: KnowledgeBaseConfig }
  ): Promise<KnowledgeBase> => {
    return apiClient.patch<KnowledgeBase>(`/api/knowledge-bases/${id}`, data);
  },

  /**
   * Delete a knowledge base
   */
  delete: async (id: string): Promise<void> => {
    return apiClient.delete<void>(`/api/knowledge-bases/${id}`);
  },

  /**
   * List articles in a knowledge base
   */
  listArticles: async (kbId: string): Promise<ListArticlesResponse> => {
    return apiClient.get<ListArticlesResponse>(`/api/knowledge-bases/${kbId}/articles`);
  },

  /**
   * Add an article to a knowledge base
   */
  addArticle: async (kbId: string, title: string): Promise<Article> => {
    return apiClient.post<Article>(`/api/knowledge-bases/${kbId}/articles`, { title });
  },

  /**
   * Delete an article
   */
  deleteArticle: async (kbId: string, articleId: string): Promise<void> => {
    return apiClient.delete<void>(`/api/knowledge-bases/${kbId}/articles/${articleId}`);
  },

  /**
   * Generate content for an article using streaming
   */
  generateArticle: async (
    kbId: string,
    articleId: string,
    onUpdate: (event: GenerateEvent) => void
  ): Promise<void> => {
    const token = await apiClient.getAuthToken();
    const response = await fetch(`/api/knowledge-bases/${kbId}/articles/${articleId}/generate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to generate article: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            try {
              const event = JSON.parse(data) as GenerateEvent;
              onUpdate(event);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },
};

export type GenerateEvent =
  | { type: 'context_start' }
  | { type: 'context_complete'; context: string }
  | { type: 'field_start'; field_name: string }
  | { type: 'field_complete'; field_name: string; content: string }
  | { type: 'field_error'; field_name: string; error: string }
  | { type: 'complete'; content: Record<string, string> }
  | { type: 'error'; error: string };
