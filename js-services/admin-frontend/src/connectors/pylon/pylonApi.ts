import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const connectPylon = (apiKey: string): Promise<void> =>
  apiClient.post('/api/pylon/connect', { apiKey });

const disconnectPylon = (): Promise<void> => apiClient.post('/api/pylon/disconnect');

const useDisconnectPylon = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: disconnectPylon,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

const useConnectPylon = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: connectPylon,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useConnectPylon, useDisconnectPylon };
