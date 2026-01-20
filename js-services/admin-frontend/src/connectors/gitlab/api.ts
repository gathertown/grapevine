import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

interface GitLabStatus {
  connected: boolean;
  configured: boolean;
  username?: string;
  name?: string;
}

interface GitLabCallbackRequest {
  code: string;
  state: string;
  redirectUri: string;
}

interface GitLabCallbackResponse {
  success: boolean;
  redirectTo?: string | null;
}

export const useGitLabStatus = () => {
  return useQuery({
    queryKey: ['gitlab', 'status'],
    queryFn: () => apiClient.get<GitLabStatus>('/api/gitlab/status'),
  });
};

export const useGitLabCallback = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: GitLabCallbackRequest) =>
      apiClient.post<GitLabCallbackResponse>('/api/gitlab/callback', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['connector-statuses'] });
    },
  });
};

export const useGitLabDisconnect = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiClient.delete('/api/gitlab/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['connector-statuses'] });
    },
  });
};
