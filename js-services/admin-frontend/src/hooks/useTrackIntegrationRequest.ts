import { useCallback } from 'react';
import { getConfig } from '../lib/config';

/**
 * Hook to track when a user requests/starts setting up an integration
 */
export function useTrackIntegrationRequest() {
  const trackIntegrationRequest = useCallback(async (integrationType: string) => {
    try {
      const config = getConfig();
      const frontendUrl = config.FRONTEND_URL || '';
      const response = await fetch(`${frontendUrl}/api/integrations/track-request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ integration: integrationType }),
      });

      if (!response.ok) {
        console.warn('Failed to track integration request:', response.statusText);
      }
    } catch (error) {
      // Silently fail - this is analytics, shouldn't affect user experience
      console.warn('Error tracking integration request:', error);
    }
  }, []);

  return { trackIntegrationRequest };
}
