/**
 * API client for Linear endpoints
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';

export interface LinearTeam {
  id: string;
  name: string;
  key: string;
}

interface LinearTeamsResponse {
  teams: LinearTeam[];
}

/**
 * Fetch Linear teams using backend endpoint (with automatic token refresh)
 */
export const useLinearTeams = () => {
  return useQuery<LinearTeam[]>({
    queryKey: ['linear', 'teams'],
    queryFn: async () => {
      const response = await apiClient.get<LinearTeamsResponse>('/api/linear/teams');
      return response.teams;
    },
    retry: 1,
    staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
  });
};
