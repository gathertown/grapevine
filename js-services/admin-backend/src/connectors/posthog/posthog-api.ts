import { logger } from '../../utils/logger';

interface PostHogMeResponse {
  id: number;
  uuid: string;
  distinct_id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
}

interface PostHogProject {
  id: number;
  uuid: string;
  name: string;
  api_token: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface PostHogProjectsResponse {
  count: number;
  results: PostHogProject[];
  next: string | null;
}

/**
 * Verify PostHog API key by fetching the current user.
 */
async function verifyPostHogApiKey(apiKey: string, host: string): Promise<PostHogMeResponse> {
  const baseUrl = host.replace(/\/$/, '');
  const response = await fetch(`${baseUrl}/api/users/@me/`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    logger.error(`Failed to verify PostHog API key: ${response.status}, ${body}`);
    throw Error('Failed to verify PostHog API key. Please check your API key and host.');
  }

  const res: PostHogMeResponse = await response.json();

  if (!res.email) {
    logger.error(`Failed to verify PostHog API key: no user email returned`);
    throw Error('Failed to verify PostHog API key');
  }

  return res;
}

/**
 * Fetch all accessible projects from PostHog.
 */
async function fetchPostHogProjects(apiKey: string, host: string): Promise<PostHogProject[]> {
  const baseUrl = host.replace(/\/$/, '');
  const allProjects: PostHogProject[] = [];
  let offset = 0;
  const limit = 100;

  while (true) {
    const response = await fetch(`${baseUrl}/api/projects/?limit=${limit}&offset=${offset}`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
    });

    if (!response.ok) {
      const body = await response.text();
      logger.error(`Failed to fetch PostHog projects: ${response.status}, ${body}`);
      throw Error('Failed to fetch PostHog projects. Please check your API key and permissions.');
    }

    const res: PostHogProjectsResponse = await response.json();
    allProjects.push(...res.results);

    if (!res.next || res.results.length < limit) {
      break;
    }

    offset += limit;
  }

  return allProjects;
}

export { verifyPostHogApiKey, fetchPostHogProjects };
export type { PostHogMeResponse, PostHogProject };
