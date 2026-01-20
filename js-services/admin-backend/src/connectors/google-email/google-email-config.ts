import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isGoogleEmailComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Google Email is complete if admin email is configured
  const adminEmail = configString(config.GOOGLE_EMAIL_ADMIN_EMAIL);
  return adminEmail.trim().length > 0;
};

export { isGoogleEmailComplete };
