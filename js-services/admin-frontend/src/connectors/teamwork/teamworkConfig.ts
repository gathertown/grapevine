const teamworkAccessTokenConfigKey = 'TEAMWORK_ACCESS_TOKEN';
const teamworkUserIdConfigKey = 'TEAMWORK_USER_ID';
const teamworkUserNameConfigKey = 'TEAMWORK_USER_NAME';
const teamworkApiDomainConfigKey = 'TEAMWORK_API_DOMAIN';

type TeamworkConfig = {
  [teamworkAccessTokenConfigKey]?: string;
  [teamworkUserIdConfigKey]?: string;
  [teamworkUserNameConfigKey]?: string;
  [teamworkApiDomainConfigKey]?: string;
};

export {
  type TeamworkConfig,
  teamworkAccessTokenConfigKey,
  teamworkUserIdConfigKey,
  teamworkUserNameConfigKey,
  teamworkApiDomainConfigKey,
};
