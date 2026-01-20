import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface IntercomStatus {
  connected: boolean;
  configured: boolean;
}

const fetchIntercomStatus = (): Promise<IntercomStatus> =>
  apiClient.get<IntercomStatus>('/api/intercom/status');

const intercomStatusQueryKey = [...connectorConfigQueryKey, 'intercom'];

const useIntercomStatus = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: intercomStatusQueryKey,
    queryFn: fetchIntercomStatus,
  });

  return { data, isLoading, error };
};

const disconnectIntercom = (): Promise<{ success: boolean }> =>
  apiClient.delete<{ success: boolean }>('/api/intercom/disconnect');

const useIntercomDisconnect = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: disconnectIntercom,
    onSuccess: () => {
      // Invalidate and refetch Intercom status
      queryClient.invalidateQueries({ queryKey: intercomStatusQueryKey });
      // Also invalidate the general config query
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });
};

export { type IntercomStatus, useIntercomStatus, useIntercomDisconnect, intercomStatusQueryKey };
