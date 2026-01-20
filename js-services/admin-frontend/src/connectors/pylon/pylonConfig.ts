const pylonApiKeyConfigKey = 'PYLON_API_KEY';

type PylonConfig = {
  [pylonApiKeyConfigKey]?: string;
};

export { type PylonConfig, pylonApiKeyConfigKey };
