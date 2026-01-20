import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isGoogleDriveComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Google Drive is complete if admin email is configured
  const adminEmail = configString(config.GOOGLE_DRIVE_ADMIN_EMAIL);
  return adminEmail.trim().length > 0;
};

export { isGoogleDriveComplete };
