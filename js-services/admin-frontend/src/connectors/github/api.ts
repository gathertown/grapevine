import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface GithubStatus {
  installed: boolean;
  type?: 'github_app' | 'pat';
  installation_id?: string;
}

const fetchGithubStatus = (): Promise<GithubStatus> =>
  apiClient.get<GithubStatus>('/api/github/status');

const githubStatusQueryKey = [...connectorConfigQueryKey, 'github'];

type UseGithubStatusOptions = Pick<UseQueryOptions<GithubStatus>, 'refetchInterval'>;

const useGithubStatus = (options?: UseGithubStatusOptions) => {
  const { data, isLoading, error } = useQuery({
    queryKey: githubStatusQueryKey,
    queryFn: fetchGithubStatus,
    ...options,
  });

  return { data, isLoading, error };
};

export { type GithubStatus, useGithubStatus, fetchGithubStatus, githubStatusQueryKey };
