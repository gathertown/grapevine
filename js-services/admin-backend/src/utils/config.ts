/**
 * Configuration utilities for admin backend
 */

export function getBaseDomain(): string {
  const baseDomain = process.env.BASE_DOMAIN;
  if (!baseDomain) {
    throw new Error('BASE_DOMAIN environment variable is required');
  }
  return baseDomain;
}

export function getFrontendUrl(): string {
  const frontendUrl = process.env.FRONTEND_URL;
  if (!frontendUrl) {
    throw new Error('FRONTEND_URL environment variable is required');
  }
  return frontendUrl;
}

export function getGatekeeperUrl(): string {
  const gatekeeperUrl = process.env.GATEKEEPER_URL;
  if (!gatekeeperUrl) {
    throw new Error('GATEKEEPER_URL environment variable is required');
  }
  return gatekeeperUrl;
}

/**
 * Check if billing is enabled for this deployment.
 * Billing is enabled when STRIPE_SECRET_KEY is configured.
 * No separate toggle needed - if Stripe is configured, billing is on.
 */
export function isBillingEnabled(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY);
}
