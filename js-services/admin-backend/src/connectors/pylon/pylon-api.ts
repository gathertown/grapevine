import { logger } from '../../utils/logger';

interface PylonMeResponse {
  data: {
    id: string;
    name: string;
  };
}

async function fetchPylonOrgId(apiKey: string): Promise<string> {
  const response = await fetch('https://api.usepylon.com/me', {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    logger.error(`Failed to fetch Pylon organization ID: ${response.status}, ${body}`);
    throw Error('Failed to fetch Pylon organization ID. Please check your API key.');
  }

  const res: PylonMeResponse = await response.json();

  if (!res.data?.id) {
    logger.error(`Failed to fetch Pylon organization ID: no data returned`);
    throw Error('Failed to fetch Pylon organization ID');
  }

  return res.data.id;
}

export { fetchPylonOrgId };
