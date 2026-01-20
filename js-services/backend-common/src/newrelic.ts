import type newrelic from 'newrelic';
import { getGrapevineEnv } from './utils';

export type NewRelic = typeof newrelic;

export const isNewRelicEnabled =
  Boolean(process.env.NEW_RELIC_LICENSE_KEY) &&
  ['staging', 'production'].includes(getGrapevineEnv());

export let nr: NewRelic | undefined = undefined;

// Defer initialization as `newrelic` automatically initialises itself on import
export function initializeNewRelicIfEnabled(baseAppName: string): NewRelic | undefined {
  if (nr !== undefined) {
    return nr;
  }
  if (isNewRelicEnabled) {
    process.env.NEW_RELIC_ENABLED = 'true';
    process.env.NEW_RELIC_APP_NAME = getNewRelicAppNameForCurrentEnv(baseAppName);
    // we want to avoid importing newrelic if it is not required, so the dynamic import is required
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    nr = require('newrelic');
    return nr;
  }
  return undefined;
}

const getNewRelicAppNameForCurrentEnv = (baseAppName: string) => {
  const envSuffixes: Record<string, string> = {
    production: 'prod',
    staging: 'staging',
    development: 'dev',
    test: 'test',
    local: 'local',
  };
  const envSuffix = envSuffixes[getGrapevineEnv()] ?? 'local';

  return `${baseAppName}-${envSuffix}`;
};
