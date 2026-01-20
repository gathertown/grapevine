import { getConfig } from '../../lib/config';

const getGitLabClientId = (): string => {
  const config = getConfig();
  const clientId = config.GITLAB_CLIENT_ID;

  if (!clientId) {
    console.error(
      'GITLAB_CLIENT_ID is not configured. Please set VITE_GITLAB_CLIENT_ID in your environment variables.'
    );
    throw new Error(
      'GitLab client ID is not configured. Please contact your administrator to set up the GitLab OAuth application ID.'
    );
  }

  return clientId;
};

/**
 * GitLab OAuth scopes for read access
 * See: https://docs.gitlab.com/ee/integration/oauth_provider.html#authorized-applications
 */
const GITLAB_SCOPES = [
  'read_user', // Read the authenticated user's personal information
  'read_api', // Read access to the API
  'read_repository', // Read access to repositories
].join(' ');

/**
 * Redirects to GitLab authorization page
 * Uses OAuth 2.0 authorization code flow
 */
export const authorizeGitLab = (): void => {
  const clientId = getGitLabClientId();

  // Use React route for callback (frontend handles OAuth callback)
  const redirectUri = `${window.location.origin}/integrations/gitlab/callback`;

  // Generate state for CSRF protection
  const state = crypto.randomUUID();

  // Store state in sessionStorage for validation on callback
  sessionStorage.setItem('gitlab_oauth_state', state);

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    state,
    scope: GITLAB_SCOPES,
  });

  const authUrl = `https://gitlab.com/oauth/authorize?${params.toString()}`;

  // Redirect to GitLab authorization
  window.location.href = authUrl;
};
