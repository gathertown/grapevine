import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';

interface SnowflakeOAuthParams {
  accountIdentifier: string;
  clientId: string;
  clientSecret: string;
  authorizationEndpoint?: string;
  tokenEndpoint?: string;
}

interface SnowflakeStatus {
  connected: boolean;
  isConfigured: boolean;
  accountIdentifier?: string;
  username?: string;
  tokenExpiry?: string;
  message: string;
}

interface TestConnectionResponse {
  success: boolean;
  message: string;
  accountIdentifier?: string;
  username?: string;
  tokenExpiry?: string;
  tokenExpired?: boolean;
}

export enum SemanticModelType {
  MODEL = 'model',
  VIEW = 'view',
}

export enum SemanticModelState {
  ENABLED = 'enabled',
  DISABLED = 'disabled',
  DELETED = 'deleted',
  ERROR = 'error',
}

interface SemanticModel {
  id: string;
  tenant_id: string;
  name: string;
  type: SemanticModelType;
  // For semantic models (YAML files in stages)
  stage_path: string | null;
  // For semantic views (database objects)
  database_name: string | null;
  schema_name: string | null;
  // Common fields
  description: string | null;
  warehouse: string | null;
  state: SemanticModelState;
  status_description: string | null;
  created_at: string;
  updated_at: string;
}

interface CreateSemanticModelParams {
  name: string;
  type: SemanticModelType;
  // For semantic models
  stage_path?: string;
  // For semantic views
  database_name?: string;
  schema_name?: string;
  // Common fields
  description?: string;
  warehouse?: string;
}

interface UpdateSemanticModelParams {
  name?: string;
  description?: string | null;
  warehouse?: string | null;
  state?: SemanticModelState;
}

const fetchSnowflakeOauthUrl = (params: SnowflakeOAuthParams): Promise<{ url: string }> => {
  const queryParams = new URLSearchParams({
    account_identifier: params.accountIdentifier,
    client_id: params.clientId,
    client_secret: params.clientSecret,
  });

  // Add optional endpoint parameters if provided
  if (params.authorizationEndpoint) {
    queryParams.append('authorization_endpoint', params.authorizationEndpoint);
  }
  if (params.tokenEndpoint) {
    queryParams.append('token_endpoint', params.tokenEndpoint);
  }

  return apiClient.get<{ url: string }>(`/api/snowflake/oauth/url?${queryParams.toString()}`);
};

const useOauthSnowflake = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async (params: SnowflakeOAuthParams) => {
      const response = await fetchSnowflakeOauthUrl(params);
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectSnowflake = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => apiClient.delete('/api/snowflake/disconnect'),
    onSuccess: () => {
      // Invalidate status query to refetch and update UI
      queryClient.invalidateQueries({ queryKey: ['snowflake', 'status'] });
      // Also invalidate config query so it refetches
      queryClient.invalidateQueries({ queryKey: ['config'] });
      // Invalidate semantic models since they depend on connection
      queryClient.invalidateQueries({ queryKey: ['snowflake', 'semantic-models'] });
    },
  });

  return { mutate, isPending, error };
};

const useSnowflakeStatus = () => {
  return useQuery<SnowflakeStatus>({
    queryKey: ['snowflake', 'status'],
    queryFn: () => apiClient.get<SnowflakeStatus>('/api/snowflake/status'),
  });
};

const useTestSnowflakeConnection = () => {
  const { mutate, isPending, data, error } = useMutation<TestConnectionResponse>({
    mutationFn: () => apiClient.post<TestConnectionResponse>('/api/snowflake/test-connection'),
  });

  return { mutate, isPending, data, error };
};

// Semantic Models hooks
const useSemanticModels = () => {
  return useQuery<{ semanticModels: SemanticModel[] }>({
    queryKey: ['snowflake', 'semantic-models'],
    queryFn: () =>
      apiClient.get<{ semanticModels: SemanticModel[] }>('/api/snowflake/semantic-models'),
  });
};

const useSemanticModel = (id: string) => {
  return useQuery<{ semanticModel: SemanticModel }>({
    queryKey: ['snowflake', 'semantic-models', id],
    queryFn: () =>
      apiClient.get<{ semanticModel: SemanticModel }>(`/api/snowflake/semantic-models/${id}`),
    enabled: !!id,
  });
};

const useCreateSemanticModel = () => {
  return useMutation<{ semanticModel: SemanticModel }, Error, CreateSemanticModelParams>({
    mutationFn: (params) =>
      apiClient.post<{ semanticModel: SemanticModel }>('/api/snowflake/semantic-models', params),
  });
};

const useUpdateSemanticModel = () => {
  return useMutation<
    { semanticModel: SemanticModel },
    Error,
    { id: string; params: UpdateSemanticModelParams }
  >({
    mutationFn: ({ id, params }) =>
      apiClient.put<{ semanticModel: SemanticModel }>(
        `/api/snowflake/semantic-models/${id}`,
        params
      ),
  });
};

const useDeleteSemanticModel = () => {
  return useMutation<{ success: boolean; deletedId: string }, Error, string>({
    mutationFn: (id) =>
      apiClient.delete<{ success: boolean; deletedId: string }>(
        `/api/snowflake/semantic-models/${id}`
      ),
  });
};

// Snowflake metadata hooks
const useSnowflakeStages = () => {
  return useQuery<{ stages: Array<{ name: string; database_name: string; schema_name: string }> }>({
    queryKey: ['snowflake', 'stages'],
    queryFn: () =>
      apiClient.get<{
        stages: Array<{ name: string; database_name: string; schema_name: string }>;
      }>('/api/snowflake/stages'),
  });
};

const useSnowflakeWarehouses = () => {
  return useQuery<{ warehouses: Array<{ name: string; size: string; state: string }> }>({
    queryKey: ['snowflake', 'warehouses'],
    queryFn: () =>
      apiClient.get<{ warehouses: Array<{ name: string; size: string; state: string }> }>(
        '/api/snowflake/warehouses'
      ),
  });
};

const useSnowflakeDatabases = () => {
  return useQuery<{ databases: Array<{ name: string; database_name: string }> }>({
    queryKey: ['snowflake', 'databases'],
    queryFn: () =>
      apiClient.get<{ databases: Array<{ name: string; database_name: string }> }>(
        '/api/snowflake/databases'
      ),
  });
};

const useSnowflakeSemanticViews = () => {
  return useQuery<{ semanticViews: Array<Record<string, unknown>> }>({
    queryKey: ['snowflake', 'semantic-views'],
    queryFn: () =>
      apiClient.get<{ semanticViews: Array<Record<string, unknown>> }>(
        '/api/snowflake/semantic-views'
      ),
  });
};

export {
  useDisconnectSnowflake,
  useOauthSnowflake,
  useSnowflakeStatus,
  useTestSnowflakeConnection,
  useSemanticModels,
  useSemanticModel,
  useCreateSemanticModel,
  useUpdateSemanticModel,
  useDeleteSemanticModel,
  useSnowflakeStages,
  useSnowflakeWarehouses,
  useSnowflakeDatabases,
  useSnowflakeSemanticViews,
  type SemanticModel,
  type CreateSemanticModelParams,
  type UpdateSemanticModelParams,
};
