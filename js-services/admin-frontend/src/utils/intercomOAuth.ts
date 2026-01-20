import { getConfig } from '../lib/config';

const getIntercomClientId = (): string => {
  const config = getConfig();
  const clientId = config.INTERCOM_CLIENT_ID;

  if (!clientId) {
    console.error(
      'INTERCOM_CLIENT_ID is not configured. Please set VITE_INTERCOM_CLIENT_ID in your environment variables.'
    );
    throw new Error(
      'Intercom client ID is not configured. Please contact your administrator to set up the Intercom OAuth client ID.'
    );
  }

  return clientId;
};

/**
 * Redirects to Intercom authorization page
 * Uses OAuth 2.0 authorization code flow
 */
export const authorizeIntercom = (): void => {
  const clientId = getIntercomClientId();

  // Use React route for callback (frontend handles OAuth callback)
  const receiverUrl = `${window.location.origin}/integrations/intercom/callback`;

  // Generate state for CSRF protection
  const state = crypto.randomUUID();

  // Store state in sessionStorage for validation on callback
  sessionStorage.setItem('intercom_oauth_state', state);

  const params = new URLSearchParams({
    client_id: clientId,
    state,
    response_type: 'code',
    redirect_uri: receiverUrl,
  });

  const authUrl = `https://app.intercom.io/oauth?${params.toString()}`;

  // Redirect to Intercom authorization
  window.location.href = authUrl;
};
