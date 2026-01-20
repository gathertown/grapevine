import { useMemo } from 'react';
import { useAuth } from './useAuth';
import { buildWebhookUrls } from '../constants';

export const useWebhookUrls = () => {
  const { user, isProvisioningComplete } = useAuth();

  // Only use tenant ID when provisioning is complete
  const tenantId = isProvisioningComplete ? user?.tenantId : null;

  return useMemo(() => {
    if (!tenantId) {
      // Return empty URLs if no tenant ID is available or provisioning not complete
      return {
        GITHUB: '',
        SLACK: '',
        NOTION: '',
        LINEAR: '',
        GATHER: '',
      };
    }

    return buildWebhookUrls(tenantId);
  }, [tenantId]);
};
