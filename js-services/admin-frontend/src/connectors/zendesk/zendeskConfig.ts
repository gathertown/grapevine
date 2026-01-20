const zendeskSubdomainConfigKey = 'ZENDESK_SUBDOMAIN';
const zendeskTokenPayloadKey = 'ZENDESK_TOKEN_PAYLOAD';

type ZendeskConfig = {
  [zendeskSubdomainConfigKey]?: string;
  [zendeskTokenPayloadKey]?: string;
};

export { type ZendeskConfig, zendeskSubdomainConfigKey, zendeskTokenPayloadKey };
