import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const fetchTeamworkOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/teamwork/install');

const useOauthTeamwork = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchTeamworkOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectTeamwork = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete('/api/teamwork/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useDisconnectTeamwork, useOauthTeamwork };
