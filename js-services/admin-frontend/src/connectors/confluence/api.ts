import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { connectorConfigQueryKey } from '../../api/config';
import { apiClient } from '../../api/client';

interface ConfluenceStatus {
  installed: boolean;
  type?: 'confluence_app';
  fully_configured?: boolean;
}

const fetchConfluenceStatus = () => apiClient.get<ConfluenceStatus>('/api/confluence/status');

const confluenceStatusQueryKey = [...connectorConfigQueryKey, 'confluence'];

type UseConfluenceStatusOptions = Pick<UseQueryOptions<ConfluenceStatus>, 'refetchInterval'>;

const useConfluenceStatus = (options?: UseConfluenceStatusOptions) => {
  const { data, isLoading, error } = useQuery({
    queryKey: confluenceStatusQueryKey,
    queryFn: fetchConfluenceStatus,
    ...options,
  });

  return { data, isLoading, error };
};

export { type ConfluenceStatus, useConfluenceStatus, confluenceStatusQueryKey };
