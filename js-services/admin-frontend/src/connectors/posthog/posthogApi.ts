import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface PostHogProject {
  id: number;
  name: string;
  uuid: string;
}

interface ConnectPostHogParams {
  apiKey: string;
  host: string;
  selectedProjectIds?: number[];
}

interface FetchProjectsParams {
  apiKey: string;
  host: string;
}

interface FetchProjectsResponse {
  projects: PostHogProject[];
}

const connectPostHog = (params: ConnectPostHogParams): Promise<void> =>
  apiClient.post('/api/posthog/connect', params);

const disconnectPostHog = (): Promise<void> => apiClient.post('/api/posthog/disconnect');

const fetchPostHogProjects = (params: FetchProjectsParams): Promise<FetchProjectsResponse> =>
  apiClient.post('/api/posthog/projects', params);

const syncPostHog = (): Promise<void> => apiClient.post('/api/posthog/sync');

const useDisconnectPostHog = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: disconnectPostHog,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

const useConnectPostHog = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: connectPostHog,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

const useFetchPostHogProjects = () => {
  const { mutate, mutateAsync, isPending, error, data } = useMutation({
    mutationFn: fetchPostHogProjects,
  });

  return { mutate, mutateAsync, isPending, error, data };
};

const useSyncPostHog = () => {
  const { mutate, isPending, error } = useMutation({
    mutationFn: syncPostHog,
  });

  return { mutate, isPending, error };
};

export { useConnectPostHog, useDisconnectPostHog, useFetchPostHogProjects, useSyncPostHog };
export type { PostHogProject };
