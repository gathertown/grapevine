import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface GongStatus {
  configured: boolean;
  access_token_present: boolean;
  api_base_url_present: boolean;
  webhook_public_key_present?: boolean;
  webhook_verified?: boolean; // Set to true when Gong sends isTest=true webhook
}

const fetchGongStatus = () => apiClient.get<GongStatus>('/api/gong/status');

const gongStatusQueryKey = [connectorConfigQueryKey, 'gong'];

type UseGongStatusOptions = Pick<UseQueryOptions<GongStatus>, 'refetchInterval'>;

const useGongStatus = (options?: UseGongStatusOptions) => {
  const { data, isLoading, error } = useQuery({
    queryKey: gongStatusQueryKey,
    queryFn: fetchGongStatus,
    ...options,
  });

  return { data, isLoading, error };
};

export { type GongStatus, useGongStatus, gongStatusQueryKey };
