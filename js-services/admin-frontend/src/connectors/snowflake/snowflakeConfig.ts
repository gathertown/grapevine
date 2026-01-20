const snowflakeOauthTokenPayloadConfigKey = 'SNOWFLAKE_OAUTH_TOKEN_PAYLOAD';
const snowflakeAccountIdentifierConfigKey = 'SNOWFLAKE_ACCOUNT_IDENTIFIER';
const snowflakeClientIdConfigKey = 'SNOWFLAKE_CLIENT_ID';
const snowflakeClientSecretConfigKey = 'SNOWFLAKE_CLIENT_SECRET';
const snowflakeOAuthAuthorizationEndpointConfigKey = 'SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT';
const snowflakeOAuthTokenEndpointConfigKey = 'SNOWFLAKE_OAUTH_TOKEN_ENDPOINT';

type SnowflakeConfig = {
  [snowflakeOauthTokenPayloadConfigKey]?: string;
  [snowflakeAccountIdentifierConfigKey]?: string;
  [snowflakeClientIdConfigKey]?: string;
  [snowflakeClientSecretConfigKey]?: string;
  [snowflakeOAuthAuthorizationEndpointConfigKey]?: string;
  [snowflakeOAuthTokenEndpointConfigKey]?: string;
};

export {
  type SnowflakeConfig,
  snowflakeOauthTokenPayloadConfigKey,
  snowflakeAccountIdentifierConfigKey,
  snowflakeClientIdConfigKey,
  snowflakeClientSecretConfigKey,
  snowflakeOAuthAuthorizationEndpointConfigKey,
  snowflakeOAuthTokenEndpointConfigKey,
};
