import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface TrelloStatus {
  configured: boolean;
  access_token_present: boolean;
  webhook_registered: boolean;
  webhook_info: {
    webhook_id: string | null;
    member_id: string | null;
    member_username: string | null;
    created_at: string | null;
  } | null;
}

const fetchTrelloStatus = (): Promise<TrelloStatus> =>
  apiClient.get<TrelloStatus>('/api/trello/status');

const trelloStatusQueryKey = [...connectorConfigQueryKey, 'trello'];

const useTrelloStatus = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: trelloStatusQueryKey,
    queryFn: fetchTrelloStatus,
  });

  return { data, isLoading, error };
};

const deleteTrelloAccessToken = (): Promise<void> =>
  apiClient.delete('/api/config/TRELLO_ACCESS_TOKEN');

const useDisconnectTrello = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: deleteTrelloAccessToken,
    onSuccess: () => {
      queryClient.setQueriesData<TrelloStatus>({ queryKey: trelloStatusQueryKey }, (previous) => ({
        ...previous,
        configured: false,
        access_token_present: false,
        webhook_registered: previous?.webhook_registered ?? false,
        webhook_info: previous?.webhook_info ?? null,
      }));
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

export { type TrelloStatus, useTrelloStatus, trelloStatusQueryKey, useDisconnectTrello };
