const firefliesApiKeyConfigKey = 'FIREFLIES_API_KEY';

type FirefliesConfig = {
  [firefliesApiKeyConfigKey]?: string;
};

export { type FirefliesConfig, firefliesApiKeyConfigKey };
