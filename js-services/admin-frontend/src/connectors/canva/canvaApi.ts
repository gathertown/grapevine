import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const fetchCanvaOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/canva/install');

const useOauthCanva = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchCanvaOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectCanva = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete('/api/canva/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useDisconnectCanva, useOauthCanva };
