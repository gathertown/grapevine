import { getConfig } from '../lib/config';

const getTrelloPowerUpApiKey = (): string => {
  const config = getConfig();
  const apiKey = config.TRELLO_POWER_UP_API_KEY;

  if (!apiKey) {
    console.error(
      'TRELLO_POWER_UP_API_KEY is not configured. Please set VITE_TRELLO_POWER_UP_API_KEY in your environment variables.'
    );
    throw new Error(
      'Trello API key is not configured. Please contact your administrator to set up the Trello Power-Up API key.'
    );
  }

  return apiKey;
};

/**
 * Redirects to Trello authorization page
 * Uses a redirect-based flow similar to HubSpot OAuth
 *
 * @param options - Configuration options for the authorization
 */
export const authorizeTrello = (options?: {
  scope?: 'read' | 'write' | 'read,write' | 'account';
  expiration?: '1hour' | '1day' | '30days' | 'never';
  name?: string;
}): void => {
  const apiKey = getTrelloPowerUpApiKey();

  // Use React route for callback
  const receiverUrl = `${window.location.origin}/integrations/trello/callback`;

  const params = new URLSearchParams({
    key: apiKey,
    name: options?.name || 'Grapevine',
    scope: options?.scope || 'read',
    expiration: options?.expiration || 'never',
    response_type: 'token',
    return_url: receiverUrl,
  });

  const authUrl = `https://trello.com/1/authorize?${params.toString()}`;

  // Redirect to Trello authorization
  window.location.href = authUrl;
};

/**
 * Validates a Trello OAuth token format
 *
 * @param token - The token to validate
 * @returns True if the token appears to be valid, false otherwise
 */
export const validateTrelloToken = (token: string): boolean => {
  if (!token || typeof token !== 'string') {
    return false;
  }

  const trimmedToken = token.trim();

  // Trello tokens start with "ATTA" prefix followed by alphanumeric characters
  if (!trimmedToken.startsWith('ATTA')) {
    return false;
  }

  // Check minimum length (ATTA + at least some characters)
  if (trimmedToken.length < 20) {
    return false;
  }

  // Check if it contains only valid characters (alphanumeric)
  const validPattern = /^ATTA[a-zA-Z0-9]+$/;
  return validPattern.test(trimmedToken);
};
