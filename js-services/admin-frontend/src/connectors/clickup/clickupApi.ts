import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const fetchClickupOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/clickup/oauth/url');

const useOauthClickup = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchClickupOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectClickup = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.post('/api/clickup/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useDisconnectClickup, useOauthClickup };
