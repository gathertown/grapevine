import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const validateTrelloToken = (token: string): boolean => {
  if (!token || typeof token !== 'string') {
    return false;
  }

  const trimmedToken = token.trim();

  // Trello tokens start with "ATTA" prefix followed by alphanumeric characters
  if (!trimmedToken.startsWith('ATTA')) {
    return false;
  }

  // Check minimum length (ATTA + at least some characters)
  if (trimmedToken.length < 20) {
    return false;
  }

  // Check if it contains only valid characters (alphanumeric)
  const validPattern = /^ATTA[a-zA-Z0-9]+$/;
  return validPattern.test(trimmedToken);
};

const isTrelloComplete = (config: Record<ConfigKey, ConfigValue>) => {
  return validateTrelloToken(configString(config.TRELLO_ACCESS_TOKEN));
};

export { isTrelloComplete };
