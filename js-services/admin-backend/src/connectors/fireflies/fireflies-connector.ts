import { installConnector, uninstallConnector } from '../../dal/connector-utils';
import { ConnectorType } from '../../types/connector';

import { fetchFirefliesUserId } from './fireflies-api';

const installFirefliesConnector = async (tenantId: string, apiKey: string) => {
  // Fetch and store user ID in connector installation
  const userId = await fetchFirefliesUserId(apiKey);

  const success = await installConnector({
    tenantId,
    type: ConnectorType.Fireflies,
    externalId: userId,
  });

  if (!success) {
    throw new Error('Failed to install Fireflies connector');
  }
};

// Uninstall can return false if no connector was found or error, we'll treat it as success
const uninstallFirefliesConnector = async (tenantId: string) => {
  await uninstallConnector(tenantId, ConnectorType.Fireflies);
};

export { installFirefliesConnector, uninstallFirefliesConnector };
