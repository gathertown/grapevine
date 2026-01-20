import { Router } from 'express';
import { ConnectorStore } from '../connectors/common/connector-store';
import { requireAdmin } from '../middleware/auth-middleware';
import { getAllConfigValues } from '../config';
import { ConnectorInstallationsRepository } from '../dal/connector-installations';
import { ConnectorType } from '../types/connector';

const connectorStatusRouter = Router();

interface ConnectorStatus {
  source: string;
  isComplete: boolean;
}

interface ConnectorStatusRes {
  connectors: ConnectorStatus[];
}

connectorStatusRouter.get('/', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'No tenant found for organization',
    });
  }

  const connectorStore = new ConnectorStore();
  const connectors = await connectorStore.getAllConnectors();
  const allConfig = await getAllConfigValues(tenantId);

  // Check for GitHub App installation from connector_installations table
  const connectorsRepo = new ConnectorInstallationsRepository();
  const ghConnectorInstallation = await connectorsRepo.getByTenantAndType(
    tenantId,
    ConnectorType.GitHub
  );

  const response: ConnectorStatusRes = {
    connectors: connectors.map((c) => ({
      source: c.source,
      isComplete: c.isComplete(allConfig, { ghInstalled: !!ghConnectorInstallation }),
    })),
  };

  res.json(response);
});

export { connectorStatusRouter };
