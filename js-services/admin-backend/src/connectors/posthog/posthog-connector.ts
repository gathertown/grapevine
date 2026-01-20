import { installConnector, uninstallConnector } from '../../dal/connector-utils';
import { ConnectorType } from '../../types/connector';

import { verifyPostHogApiKey } from './posthog-api';
import { resetPostHogBackfillState } from './posthog-config';

interface InstallPostHogConnectorOptions {
  tenantId: string;
  apiKey: string;
  host: string;
  selectedProjectIds?: number[];
}

const installPostHogConnector = async ({
  tenantId,
  apiKey,
  host,
  selectedProjectIds,
}: InstallPostHogConnectorOptions) => {
  // Verify API key and fetch user info for external_id
  const user = await verifyPostHogApiKey(apiKey, host);

  const success = await installConnector({
    tenantId,
    type: ConnectorType.PostHog,
    externalId: user.uuid,
    externalMetadata: {
      user_email: user.email,
      host,
      selected_project_ids: selectedProjectIds ?? [],
      synced_project_ids: [],
    },
    updateMetadataOnExisting: true,
  });

  if (!success) {
    throw new Error('Failed to install PostHog connector');
  }

  // Reset backfill state to ensure fresh sync on reconnect
  await resetPostHogBackfillState(tenantId);
};

// Uninstall can return false if no connector was found or error, we'll treat it as success
const uninstallPostHogConnector = async (tenantId: string) => {
  await uninstallConnector(tenantId, ConnectorType.PostHog);
};

export { installPostHogConnector, uninstallPostHogConnector };
