import crypto from 'node:crypto';

import { getOrInitializeRedis } from '../../redis-client';

interface StoredOauthState {
  stateString: string;
  tenantId: string;
  subdomain: string;
  codeVerifier: string;
  codeChallenge: string;
}

const buildOauthStateString = () => crypto.randomBytes(16).toString('hex');

// Zendesk wants a code_verifier between 43 and 128 characters, 50 bytes will be longer once base64url-encoded
const buildOauthCodeVerifier = () => crypto.randomBytes(50).toString('base64url');

const buildOauthCodeChallenge = (input: string) =>
  crypto.createHash('sha256').update(input).digest('base64url');

const buildRedisKey = (stateString: string) => `zendesk_oauth_state:${stateString}`;

/**
 * Generate and store a new OAuth state for Zendesk OAuth flow.
 */
const generateOauthState = async ({
  tenantId,
  subdomain,
}: {
  tenantId: string;
  subdomain: string;
}): Promise<StoredOauthState> => {
  const redis = getOrInitializeRedis();
  if (!redis) {
    throw new Error('Redis not configured - cannot retrieve OAuth state');
  }

  const stateString = buildOauthStateString();
  const codeVerifier = buildOauthCodeVerifier();
  const codeChallenge = buildOauthCodeChallenge(codeVerifier);

  const storedState: StoredOauthState = {
    stateString,
    tenantId,
    subdomain,
    codeVerifier,
    codeChallenge,
  };

  // Expire these pretty quickly, oauth codes are short-lived anyways
  const fiveMinsInSeconds = 5 * 60;
  await redis.set(buildRedisKey(stateString), JSON.stringify(storedState), 'EX', fiveMinsInSeconds);

  return storedState;
};

const retrieveOauthState = async (stateString: string): Promise<StoredOauthState | null> => {
  const redis = getOrInitializeRedis();
  if (!redis) {
    throw new Error('Redis not configured - cannot retrieve OAuth state');
  }

  const data = await redis.get(buildRedisKey(stateString));
  if (!data) {
    return null;
  }

  return JSON.parse(data) as StoredOauthState;
};

const ZendeskOauthStore = {
  generateOauthState,
  retrieveOauthState,
};

export { ZendeskOauthStore, type StoredOauthState };
