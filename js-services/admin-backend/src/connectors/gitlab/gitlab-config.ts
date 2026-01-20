import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isGitlabComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Check for GitLab OAuth access token
  const gitlabAccessToken = configString(config.GITLAB_ACCESS_TOKEN);
  return gitlabAccessToken.trim().length > 10;
};

export { isGitlabComplete };
