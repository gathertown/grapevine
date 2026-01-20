/**
 * Get the current Grapevine environment based on the hostname
 * @returns 'local' | 'staging' | 'production'
 */
export const getGrapevineEnv = (): string => {
  const hostname = window.location.hostname;

  // Determine environment based on hostname
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'local';
  } else if (hostname.includes('stg.') || hostname.includes('staging')) {
    return 'staging';
  } else if (
    hostname.includes('prod') ||
    (!hostname.includes('stg.') && !hostname.includes('staging'))
  ) {
    // Production if explicitly contains 'prod' OR if it doesn't contain staging indicators
    return 'production';
  }

  // Default to production for safety
  return 'production';
};
