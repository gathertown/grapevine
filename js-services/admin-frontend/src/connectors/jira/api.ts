import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey } from '../../api/config';

interface JiraStatus {
  installed: boolean;
  type?: 'jira_app';
  fully_configured?: boolean;
}

const fetchJiraStatus = (): Promise<JiraStatus> => apiClient.get<JiraStatus>('/api/jira/status');

const jiraStatusQueryKey = [...connectorConfigQueryKey, 'jira'];

type UseJiraStatusOptions = Pick<UseQueryOptions<JiraStatus>, 'refetchInterval'>;

const useJiraStatus = (options?: UseJiraStatusOptions) => {
  const { data, isLoading, error } = useQuery({
    queryKey: jiraStatusQueryKey,
    queryFn: fetchJiraStatus,
    ...options,
  });

  return { data, isLoading, error };
};

export { type JiraStatus, useJiraStatus, jiraStatusQueryKey };
