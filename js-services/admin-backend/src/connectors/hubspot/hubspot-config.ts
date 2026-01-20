import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isHubspotComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // HubSpot is complete if HUBSPOT_COMPLETE flag is true
  return configString(config.HUBSPOT_COMPLETE) === 'true';
};

export { isHubspotComplete };
