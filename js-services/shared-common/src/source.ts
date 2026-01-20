/**
 * Source Enum
 * Defines valid source values for tenants/organizations
 */

export enum Source {
  Docs = 'docs',
  LandingPage = 'landing_page',
}

/**
 * Type guard to check if a value is a valid Source
 */
export function isValidSource(value: unknown): value is Source {
  return typeof value === 'string' && Object.values(Source).includes(value as Source);
}
