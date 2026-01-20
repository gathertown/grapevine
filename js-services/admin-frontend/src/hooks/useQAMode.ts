import { useAllConfig } from '../api/config';
import { TenantMode } from '@corporate-context/shared-common';

export const useQAMode = (): boolean => {
  const { data: configData } = useAllConfig();
  return configData?.TENANT_MODE === TenantMode.QA;
};
