import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const connectFireflies = (apiKey: string): Promise<void> =>
  apiClient.post('/api/fireflies/connect', { apiKey });

const disconnectFireflies = (): Promise<void> => apiClient.post('/api/fireflies/disconnect');

const useDisconnectFireflies = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: disconnectFireflies,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

const useConnectFireflies = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: connectFireflies,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { useConnectFireflies, useDisconnectFireflies };
