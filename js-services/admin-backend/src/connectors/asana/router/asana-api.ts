import { logger } from '../../../utils/logger';

interface AsanaWorkspace {
  gid: string;
  name: string;
  resource_type: 'workspace';
}

interface AsanaWorkspacesResponse {
  data: AsanaWorkspace[];
}

async function fetchAsanaWorkspace(accessToken: string): Promise<string | null> {
  try {
    const response = await fetch('https://app.asana.com/api/1.0/workspaces', {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      logger.error('Failed to fetch Asana workspace', { status: response.status });
      return null;
    }

    const data: AsanaWorkspacesResponse = await response.json();
    const workspace = data.data?.[0];

    if (workspace?.gid) {
      logger.info('Fetched Asana workspace', { workspaceId: workspace.gid });
      return workspace.gid;
    }

    logger.warn('No workspace found in Asana API response');
    return null;
  } catch (error) {
    logger.error('Error fetching Asana workspace', error);
    return null;
  }
}

export { fetchAsanaWorkspace };
