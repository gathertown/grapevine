import { logger } from '../../utils/logger';

interface Workspace {
  id: string;
  name: string;
}

interface ClickupWokspacesResponse {
  teams: Workspace[];
}

async function fetchClickupAuthorizedWorkspaces(token: string): Promise<Workspace[]> {
  const response = await fetch('https://api.clickup.com/api/v2/team', {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    logger.error(`Failed to fetch ClickUp authorized workspaces: ${response.status}, ${body}`);
    throw Error('Failed to fetch ClickUp authorized workspaces');
  }

  const res: ClickupWokspacesResponse = await response.json();

  return res.teams;
}

export { fetchClickupAuthorizedWorkspaces };
