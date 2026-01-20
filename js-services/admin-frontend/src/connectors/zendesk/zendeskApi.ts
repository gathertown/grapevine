import { useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useDeleteConfigValue } from '../../api/config';
import { zendeskSubdomainConfigKey, zendeskTokenPayloadKey } from './zendeskConfig';

interface FetchZendeskOauthUrlReq {
  subdomain: string;
}

const fetchZendeskOauthUrl = ({ subdomain }: FetchZendeskOauthUrlReq): Promise<{ url: string }> => {
  const baseUrl = '/api/zendesk/oauth/url';
  const queryString = new URLSearchParams({
    subdomain,
  }).toString();

  return apiClient.get<{ url: string }>(`${baseUrl}?${queryString}`);
};

const useDisconnectZendesk = () => {
  const { mutateAsync: deleteConfig } = useDeleteConfigValue();

  const { mutate, isPending, error } = useMutation({
    mutationFn: () =>
      Promise.all([
        deleteConfig({ key: zendeskTokenPayloadKey }),
        deleteConfig({ key: zendeskSubdomainConfigKey }),
      ]),
  });

  return { mutate, isPending, error };
};

const useOauthZendesk = () => {
  const { mutate, isPending, isSuccess, error } = useMutation({
    mutationFn: async (subdomain: string) => {
      const response = await fetchZendeskOauthUrl({ subdomain });
      window.location.href = response.url;
    },
  });

  return { mutate, isPending, isSuccess, error };
};

export { useDisconnectZendesk, useOauthZendesk };
