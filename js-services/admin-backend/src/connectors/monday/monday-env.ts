/**
 * Monday.com environment variable accessors
 *
 * These are used for OAuth authentication.
 */

export function getMondayClientId(): string {
  const value = process.env.MONDAY_CLIENT_ID;
  if (!value) {
    throw new Error('MONDAY_CLIENT_ID environment variable is required for Monday.com OAuth');
  }
  return value;
}

export function getMondayClientSecret(): string {
  const value = process.env.MONDAY_CLIENT_SECRET;
  if (!value) {
    throw new Error('MONDAY_CLIENT_SECRET environment variable is required for Monday.com OAuth');
  }
  return value;
}

export function getMondaySigningSecret(): string {
  const value = process.env.MONDAY_SIGNING_SECRET;
  if (!value) {
    throw new Error(
      'MONDAY_SIGNING_SECRET environment variable is required for Monday.com webhooks'
    );
  }
  return value;
}
