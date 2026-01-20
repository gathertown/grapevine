import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const fetchMondayOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/monday/install');

const useOauthMonday = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchMondayOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectMonday = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete('/api/monday/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useDisconnectMonday, useOauthMonday };
