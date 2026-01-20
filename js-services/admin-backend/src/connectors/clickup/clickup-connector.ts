import { installConnector, uninstallConnector } from '../../dal/connector-utils';
import { ConnectorType } from '../../types/connector';

import { fetchClickupAuthorizedWorkspaces } from './clickup-api';

const installClickupConnector = async (tenantId: string, token: string) => {
  // Fetch and store user ID in connector installation
  const workspaces = await fetchClickupAuthorizedWorkspaces(token);
  const workspaceIds = workspaces.map((ws) => ws.id).sort();

  const workspaceId = workspaceIds[0];
  if (!workspaceId) {
    throw new Error('No Clickup workspaces found for installation');
  }

  const success = await installConnector({
    tenantId,
    type: ConnectorType.Clickup,
    externalId: workspaceId,
  });

  if (!success) {
    throw new Error('Failed to install Clickup connector');
  }
};

// Uninstall can return false if no connector was found or error, we'll treat it as success
const uninstallClickupConnector = async (tenantId: string) => {
  await uninstallConnector(tenantId, ConnectorType.Clickup);
};

export { installClickupConnector, uninstallClickupConnector };
