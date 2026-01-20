import { logger } from '../../utils/logger';

interface FirefliesUserResponse {
  errors: unknown[];
  data: {
    user: {
      user_id: string;
    };
  };
}

async function fetchFirefliesUserId(apiKey: string): Promise<string> {
  const response = await fetch('https://api.fireflies.ai/graphql', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ query: 'query{user{user_id}}' }),
  });

  if (!response.ok) {
    const body = await response.text();
    logger.error(`Failed to fetch Fireflies user ID: ${response.status}, ${body}`);
    throw Error('Failed to fetch Fireflies user ID');
  }

  const res: FirefliesUserResponse = await response.json();

  if (res.errors && res.errors.length > 0) {
    logger.error(`Failed to fetch Fireflies user ID: ${JSON.stringify(res.errors)}`);
    throw Error('Failed to fetch Fireflies user ID');
  }

  return res.data.user.user_id;
}

export { fetchFirefliesUserId };
