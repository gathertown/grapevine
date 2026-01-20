const asanaOauthTokenPayloadConfigKey = 'ASANA_OAUTH_TOKEN_PAYLOAD';
const asanaServiceAccountTokenConfigKey = 'ASANA_SERVICE_ACCOUNT_TOKEN';

type AsanaConfig = {
  [asanaOauthTokenPayloadConfigKey]?: string;
  [asanaServiceAccountTokenConfigKey]?: string;
};

export { type AsanaConfig, asanaOauthTokenPayloadConfigKey, asanaServiceAccountTokenConfigKey };
