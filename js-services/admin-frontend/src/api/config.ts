import { useMutation, useQuery, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { apiClient } from './client';
import { ZendeskConfig } from '../connectors/zendesk/zendeskConfig';
import { useAuth } from '../hooks/useAuth';
import { AsanaConfig } from '../connectors/asana/asanaConfig';
import { SnowflakeConfig } from '../connectors/snowflake/snowflakeConfig';
import { FirefliesConfig } from '../connectors/fireflies/firefliesConfig';
import { ClickupConfig } from '../connectors/clickup/clickupConfig';
import { PylonConfig } from '../connectors/pylon/pylonConfig';
import { MondayConfig } from '../connectors/monday/mondayConfig';
import { PipedriveConfig } from '../connectors/pipedrive/pipedriveConfig';
import { FigmaConfig } from '../connectors/figma/figmaConfig';
import { CanvaConfig } from '../connectors/canva/canvaConfig';
import { TeamworkConfig } from '../connectors/teamwork/teamworkConfig';

type ConfigData = {
  COMPANY_NAME?: string;
  COMPANY_CONTEXT?: string;
  TENANT_MODE?: string;
  SLACK_BOT_NAME?: string;
  SLACK_BOT_TOKEN?: string;
  SLACK_SIGNING_SECRET?: string;
  SLACK_BOT_QA_ALL_CHANNELS?: string;
  SLACK_BOT_QA_DISALLOWED_CHANNELS?: string;
  SLACK_BOT_TESTED?: string;
  NOTION_TOKEN?: string;
  NOTION_WEBHOOK_SECRET?: string;
  GITHUB_TOKEN?: string;
  GITHUB_WEBHOOK_SECRET?: string;
  GITHUB_SETUP_COMPLETE?: string;
  LINEAR_API_KEY?: string;
  LINEAR_WEBHOOK_SECRET?: string;
  LINEAR_ACCESS_TOKEN?: string;
  LINEAR_REFRESH_TOKEN?: string;
  LINEAR_TOKEN_EXPIRES_AT?: string;
  SALESFORCE_REFRESH_TOKEN?: string;
  SALESFORCE_INSTANCE_URL?: string;
  SALESFORCE_ORG_ID?: string;
  SALESFORCE_USER_ID?: string;
  GONG_SCOPE?: string;
  GONG_TOKEN_TYPE?: string;
  GONG_TOKEN_EXPIRES_IN?: string;
  GONG_API_BASE_URL?: string;
  GATHER_API_KEY?: string;
  GATHER_WEBHOOK_SECRET?: string;
  INTERCOM_ACCESS_TOKEN?: string;
  INTERCOM_TOKEN_TYPE?: string;
} & ZendeskConfig &
  AsanaConfig &
  SnowflakeConfig &
  FirefliesConfig &
  ClickupConfig &
  PylonConfig &
  MondayConfig &
  PipedriveConfig &
  FigmaConfig &
  CanvaConfig &
  TeamworkConfig & { [key: string]: string | undefined };

interface ConfigResponse {
  data: ConfigData;
}

// Use this as the base cache key for ANYTHING that should refresh when ANY config changes
// React query will invalidate all querys based on a prefix:
// https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation#query-matching-with-invalidatequeries
const connectorConfigQueryKey = ['connector-config'];

const fetchAllConfig = (): Promise<ConfigData> =>
  apiClient.get<ConfigResponse>('/api/config/all').then(({ data }) => data);

type UseAllConfigOptions = Pick<UseQueryOptions<ConfigData>, 'refetchInterval' | 'enabled'>;

const useAllConfig = (options?: UseAllConfigOptions) => {
  const { isProvisioningComplete } = useAuth();

  const enabled = isProvisioningComplete && options?.enabled;

  const { data, isLoading, error } = useQuery({
    queryKey: connectorConfigQueryKey,
    queryFn: fetchAllConfig,
    ...options,
    enabled,
  });

  return { data, isLoading, error };
};

type SetConfigParams = {
  key: keyof ConfigData;
  value: string;
};

const setConfigValue = ({ key, value }: SetConfigParams): Promise<void> =>
  apiClient.post('/api/config/save', { key, value });

const useSetConfigValue = () => {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending, error } = useMutation({
    mutationFn: setConfigValue,
    onSuccess: (_data, { key, value }) => {
      queryClient.setQueryData<ConfigData>(connectorConfigQueryKey, (previous) => ({
        ...previous,
        [key]: value,
      }));
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutateAsync, isPending, error };
};

const deleteConfigValue = ({ key }: { key: keyof ConfigData }): Promise<void> =>
  apiClient.delete(`/api/config/${key}`);

const useDeleteConfigValue = () => {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending, error } = useMutation({
    mutationFn: deleteConfigValue,
    onSuccess: (_data, { key }) => {
      queryClient.setQueryData<ConfigData>(connectorConfigQueryKey, (previous) => {
        const { [key]: _deleted, ...rest } = previous || {};
        return rest;
      });
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutateAsync, isPending, error };
};

interface ConnectorStatus {
  source: string;
  isComplete: boolean;
}

interface ConnectorStatusRes {
  connectors: ConnectorStatus[];
}

const getAllConnectorStatuses = (): Promise<ConnectorStatus[]> =>
  apiClient.get<ConnectorStatusRes>('/api/connector-status').then(({ connectors }) => connectors);

const connectorStatusesQueryKey = [...connectorConfigQueryKey, 'connector-status'];

const useConnectorStatuses = () => {
  return useQuery({
    queryKey: connectorStatusesQueryKey,
    queryFn: getAllConnectorStatuses,
  });
};

export {
  getAllConnectorStatuses,
  type ConnectorStatus,
  type ConfigData,
  useConnectorStatuses,
  useAllConfig,
  useSetConfigValue,
  useDeleteConfigValue,
  connectorStatusesQueryKey,
  connectorConfigQueryKey,
};
