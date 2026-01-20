export const getGrapevineEnv = () => process.env.GRAPEVINE_ENVIRONMENT ?? 'local';

export enum Env {
  local = 'local',
  staging = 'staging',
  production = 'production',
}

export const currentEnv = (): Env => {
  const env = getGrapevineEnv();

  // normally I'd use enumFromValue but didn't want to make a dependency for this package
  if (!(env in Env)) throw new Error(`Unexpected environment: ${env}`);

  return Env[env as Env];
};

function resolveValue<T>(value: T | (() => T)): T {
  // if it's a function, call it, otherwise return the value, which works for
  // both null and non-function/primative values so no null check is necessary
  return value instanceof Function ? value() : value;
}

// Copied and adjusted from Gather Repo
export function switchEnv<T>(envs: { [env in Env]: (() => T) | T }, env: Env = currentEnv()) {
  const res = envs[env];
  return resolveValue(res);
}

// This map assumes environment parity between grapevine and gather, which may not always be accurate/appropriate
// for your use-case, so adjust accordingly.
export const GATHER_API_URL = switchEnv({
  local: 'http://localhost:3000/api/v2/me/api-keys',
  staging: 'https://api.v2.staging.gather.town/api/v2/me/api-keys',
  production: 'https://api.v2.gather.town/api/v2/me/api-keys',
});
