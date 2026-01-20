const pipedriveAccessTokenConfigKey = 'PIPEDRIVE_ACCESS_TOKEN';
const pipedriveApiDomainConfigKey = 'PIPEDRIVE_API_DOMAIN';
const pipedriveCompanyNameConfigKey = 'PIPEDRIVE_COMPANY_NAME';

type PipedriveConfig = {
  [pipedriveAccessTokenConfigKey]?: string;
  [pipedriveApiDomainConfigKey]?: string;
  [pipedriveCompanyNameConfigKey]?: string;
};

export {
  type PipedriveConfig,
  pipedriveAccessTokenConfigKey,
  pipedriveApiDomainConfigKey,
  pipedriveCompanyNameConfigKey,
};
