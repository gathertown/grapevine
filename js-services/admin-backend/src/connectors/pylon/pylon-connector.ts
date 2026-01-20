import { installConnector, uninstallConnector } from '../../dal/connector-utils';
import { ConnectorType } from '../../types/connector';

import { fetchPylonOrgId } from './pylon-api';
import { resetPylonBackfillState } from './pylon-config';

const installPylonConnector = async (tenantId: string, apiKey: string) => {
  // Fetch and store organization ID in connector installation
  const orgId = await fetchPylonOrgId(apiKey);

  const success = await installConnector({
    tenantId,
    type: ConnectorType.Pylon,
    externalId: orgId,
  });

  if (!success) {
    throw new Error('Failed to install Pylon connector');
  }

  // Reset backfill state to ensure fresh sync on reconnect
  await resetPylonBackfillState(tenantId);
};

// Uninstall can return false if no connector was found or error, we'll treat it as success
const uninstallPylonConnector = async (tenantId: string) => {
  await uninstallConnector(tenantId, ConnectorType.Pylon);
};

export { installPylonConnector, uninstallPylonConnector };
