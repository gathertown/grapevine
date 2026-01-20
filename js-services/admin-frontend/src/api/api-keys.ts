import { apiClient } from './client';

export interface APIKeyInfo {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  createdBy: string | null;
}

export interface CreateAPIKeyResponse {
  apiKey: string;
  keyInfo: APIKeyInfo;
}

export interface ListAPIKeysResponse {
  keys: APIKeyInfo[];
}

export const apiKeysApi = {
  /**
   * Create a new API key
   */
  createKey: async (name: string): Promise<CreateAPIKeyResponse> => {
    return apiClient.post<CreateAPIKeyResponse>('/api/api-keys', { name });
  },

  /**
   * List all API keys for the current tenant
   */
  listKeys: async (): Promise<ListAPIKeysResponse> => {
    return apiClient.get<ListAPIKeysResponse>('/api/api-keys');
  },

  /**
   * Delete an API key
   */
  deleteKey: async (keyId: string): Promise<{ success: boolean }> => {
    return apiClient.delete<{ success: boolean }>(`/api/api-keys/${keyId}`);
  },
};
