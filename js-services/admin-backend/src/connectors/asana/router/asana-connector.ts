import { installConnector } from '../../../dal/connector-utils';
import { ConnectorType } from '../../../types/connector';
import { logger } from '../../../utils/logger';

import { fetchAsanaWorkspace } from './asana-api';

const installAsanaConnector = async (tenantId: string, accessToken: string) => {
  // Fetch and store workspace ID in connector installation
  const workspaceId = await fetchAsanaWorkspace(accessToken);
  if (workspaceId && workspaceId.trim().length > 0) {
    await installConnector({
      tenantId,
      type: ConnectorType.Asana,
      externalId: workspaceId,
    });
    logger.info('Asana connector installed with workspace ID', { tenantId, workspaceId });
  } else {
    logger.warn('Asana failed to fetch workspace ID', { tenantId });
  }
};

export { installAsanaConnector };
