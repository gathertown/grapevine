import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { connectorConfigQueryKey, useDeleteConfigValue } from '../../api/config';
import { asanaOauthTokenPayloadConfigKey, asanaServiceAccountTokenConfigKey } from './asanaConfig';

const saveAsanaServiceAccountToken = (token: string): Promise<void> =>
  apiClient.post('/api/asana/service-account-auth', { token });

const fetchAsanaOauthUrl = (): Promise<{ url: string }> =>
  apiClient.get<{ url: string }>('/api/asana/oauth/url');

const useOauthAsana = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async () => {
      const response = await fetchAsanaOauthUrl();
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

const useDisconnectAsanaOauth = () => {
  const { mutateAsync: deleteConfig } = useDeleteConfigValue();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => deleteConfig({ key: asanaOauthTokenPayloadConfigKey }),
  });

  return { mutate, isPending, error };
};

const useSaveAsanaServiceAccountToken = () => {
  const queryClient = useQueryClient();

  const { mutate, isPending, error } = useMutation({
    mutationFn: saveAsanaServiceAccountToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });
    },
  });

  return { mutate, isPending, error };
};

const useDisconnectAsanaServiceAccount = () => {
  const { mutateAsync: deleteConfig } = useDeleteConfigValue();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () => deleteConfig({ key: asanaServiceAccountTokenConfigKey }),
  });

  return { mutate, isPending, error };
};

export {
  useDisconnectAsanaOauth,
  useOauthAsana,
  useSaveAsanaServiceAccountToken,
  useDisconnectAsanaServiceAccount,
};
