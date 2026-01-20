const mondayAccessTokenConfigKey = 'MONDAY_ACCESS_TOKEN';

type MondayConfig = {
  [mondayAccessTokenConfigKey]?: string;
};

export { type MondayConfig, mondayAccessTokenConfigKey };
