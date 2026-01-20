import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

const fetchFigmaOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/figma/install');

const useOauthFigma = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchFigmaOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectFigma = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete('/api/figma/disconnect'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

// Team selection hooks
const figmaTeamsQueryKey = ['figma', 'teams'];

interface FigmaTeamsResponse {
  team_ids: string[];
}

const useFigmaTeams = () => {
  return useQuery({
    queryKey: figmaTeamsQueryKey,
    queryFn: () => apiClient.get<FigmaTeamsResponse>('/api/figma/teams'),
  });
};

const useSaveFigmaTeams = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (teamIds: string[]) =>
      apiClient.post<{ success: boolean; team_ids: string[] }>('/api/figma/teams', {
        team_ids: teamIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: figmaTeamsQueryKey });
    },
  });
};

export { useDisconnectFigma, useOauthFigma, useFigmaTeams, useSaveFigmaTeams };
