import { statsApi, SourceStats } from '../api/stats';
import { useQuery, UseQueryOptions } from '@tanstack/react-query';

const sourceStatsQueryKey = ['source-stats'];

type UseSourceStatsOptions = Pick<UseQueryOptions<SourceStats>, 'enabled'>;

const useSourceStats = (options?: UseSourceStatsOptions) => {
  const { data, isLoading, error } = useQuery({
    queryKey: sourceStatsQueryKey,
    queryFn: () => statsApi.getSourceStats(),
    refetchInterval: 15_000,
    ...options,
  });

  return { data, isLoading, error };
};

export { useSourceStats, sourceStatsQueryKey };
