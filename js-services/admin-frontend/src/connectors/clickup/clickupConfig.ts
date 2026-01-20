const clickupOauthTokenConfigKey = 'CLICKUP_OAUTH_TOKEN';

type ClickupConfig = {
  [clickupOauthTokenConfigKey]?: string;
};

export { type ClickupConfig, clickupOauthTokenConfigKey };
