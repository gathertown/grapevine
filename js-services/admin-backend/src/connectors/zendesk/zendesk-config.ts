import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue } from '../../config';

const ZENDESK_SUBDOMAIN_CONFIG_KEY = 'ZENDESK_SUBDOMAIN';
const ZENDESK_TOKEN_PAYLOAD_CONFIG_KEY = 'ZENDESK_TOKEN_PAYLOAD';

const ZENDESK_SENSITIVE_KEYS = [ZENDESK_TOKEN_PAYLOAD_CONFIG_KEY] as const;

const ZENDESK_NON_SENSITIVE_KEYS = [ZENDESK_SUBDOMAIN_CONFIG_KEY] as const;

interface ZendeskToken {
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string | null;
  refresh_token_expires_at: string;
}

const saveZendeskSubdomain = async (tenantId: string, subdomain: string): Promise<void> => {
  const saved = await saveConfigValue(ZENDESK_SUBDOMAIN_CONFIG_KEY, subdomain, tenantId);
  if (!saved) {
    throw new Error('Failed to save Zendesk subdomain');
  }
};

const saveZendeskToken = async (tenantId: string, token: ZendeskToken): Promise<void> => {
  const tokenJson = JSON.stringify(token);

  const saved = await saveConfigValue(ZENDESK_TOKEN_PAYLOAD_CONFIG_KEY, tokenJson, tenantId);
  if (!saved) {
    throw new Error('Failed to save Zendesk access token');
  }
};

const isZendeskComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[ZENDESK_SUBDOMAIN_CONFIG_KEY] && !!config[ZENDESK_TOKEN_PAYLOAD_CONFIG_KEY];

export {
  isZendeskComplete,
  saveZendeskSubdomain,
  saveZendeskToken,
  ZENDESK_SENSITIVE_KEYS,
  ZENDESK_NON_SENSITIVE_KEYS,
  type ZendeskToken,
};
