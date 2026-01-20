import { UserManager, UserManagerSettings, User } from 'oidc-client-ts';
import { SALESFORCE_CLIENT_ID } from '../constants';
import { getConfig } from '../lib/config';

// Get Salesforce OAuth configuration dynamically
const getSalesforceOAuthConfig = (): UserManagerSettings => {
  const config = getConfig();
  const frontendUrl = config.FRONTEND_URL;

  if (!frontendUrl) {
    throw new Error('FRONTEND_URL configuration is required for Salesforce OAuth');
  }

  if (!SALESFORCE_CLIENT_ID) {
    throw new Error('SALESFORCE_CLIENT_ID configuration is required for Salesforce OAuth');
  }

  return {
    // Salesforce OAuth2 endpoints
    authority: 'https://login.salesforce.com',
    client_id: SALESFORCE_CLIENT_ID,
    // This must EXACTLY match the redirect URI in Salesforce!
    redirect_uri:
      window.location.hostname === 'localhost'
        ? `http://localhost:5173/integrations/salesforce/callback`
        : `${frontendUrl}/integrations/salesforce/callback`,

    // OAuth2 flow configuration
    response_type: 'code',
    scope: 'api refresh_token id',

    // Disable features not needed for Salesforce integration
    automaticSilentRenew: false,
    includeIdTokenInSilentRenew: false,
    monitorSession: false,
    validateSubOnSilentRenew: false,

    // Custom metadata for Salesforce OAuth2 (non-OIDC provider)
    metadata: {
      issuer: 'https://login.salesforce.com',
      authorization_endpoint: 'https://login.salesforce.com/services/oauth2/authorize',
      // Use our backend proxy
      token_endpoint: '/api/salesforce/oauth/token-proxy',
      // Salesforce doesn't provide these OIDC endpoints, but oidc-client-ts requires them
      userinfo_endpoint: 'https://login.salesforce.com/services/oauth2/userinfo',
      end_session_endpoint: 'https://login.salesforce.com/services/oauth2/revoke',
      code_challenge_methods_supported: ['S256'], // PKCE with SHA256
    },
  };
};

// Singleton UserManager instance
let userManager: UserManager | null = null;

export const getSalesforceOAuthManager = (): UserManager => {
  if (!userManager) {
    userManager = new UserManager(getSalesforceOAuthConfig());
  }
  return userManager;
};

// OAuth flow methods
export const startSalesforceOAuth = async (): Promise<void> => {
  const manager = getSalesforceOAuthManager();

  // Clear any existing (potentially stale) authentication state first
  await clearSalesforceAuth();

  await manager.signinRedirect({
    state: crypto.randomUUID(), // CSRF protection
    // Force fresh authentication every time
    prompt: 'login', // Forces Salesforce to show login screen
  });
};

// Tracks the promise for the Salesforce OAuth callback to prevent double execution
// (e.g. from React StrictMode). Only at most one Salesforce OAuth callback should execute
// in any given session.
let callbackPromise: Promise<User | null> | null = null;

// Handle the Salesforce OAuth callback. Future calls past the first will always return the same promise.
export const handleSalesforceOAuthCallback = async (): Promise<User | null> => {
  // If already processing, return the same promise
  if (callbackPromise) {
    return callbackPromise;
  }

  callbackPromise = (async () => {
    try {
      const manager = getSalesforceOAuthManager();
      // Let oidc-client-ts handle the full OAuth callback including PKCE validation
      const user = await manager.signinRedirectCallback();
      return user;
    } catch (error) {
      console.error('Salesforce OAuth callback error:', error);
      throw error;
    }
  })();

  return callbackPromise;
};

export const clearSalesforceAuth = async (): Promise<void> => {
  try {
    const manager = getSalesforceOAuthManager();
    await manager.removeUser();
    await manager.clearStaleState();
  } catch (error) {
    console.error('Error clearing Salesforce auth:', error);
  }
};

// Helper to extract Salesforce tokens for backend storage
export const extractSalesforceTokens = (user: User) => {
  return {
    access_token: user.access_token,
    refresh_token: user.refresh_token,
    instance_url: String(user.profile?.instance_url ?? ''),
    org_id: String(user.profile?.org_id ?? ''),
    user_id: String(user.profile?.user_id ?? ''),
  } as const;
};
