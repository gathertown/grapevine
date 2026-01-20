import { useCallback } from 'react';
import { useAnalytics } from '@corporate-context/frontend-common';
import type {
  AnalyticsEventName,
  AnalyticsEventProperties,
} from '@corporate-context/shared-common';
import { useAuth } from './useAuth';

export interface UseTrackEventReturn {
  trackEvent: <T extends AnalyticsEventName>(
    eventName: T,
    eventProperties: AnalyticsEventProperties<T>
  ) => void;
}

/**
 * Custom hook that wraps useAnalytics and automatically injects tenant_id
 * into all analytics events when not explicitly provided.
 */
export const useTrackEvent = (): UseTrackEventReturn => {
  const { trackEvent: baseTrackEvent } = useAnalytics();
  const { user } = useAuth();

  const trackEvent = useCallback(
    <T extends AnalyticsEventName>(eventName: T, eventProperties: AnalyticsEventProperties<T>) => {
      // Automatically inject tenant_id from the authenticated user if not already provided
      const enhancedProperties = {
        ...eventProperties,
        tenant_id: eventProperties.tenant_id ?? user?.tenantId,
      };

      baseTrackEvent(eventName, enhancedProperties);
    },
    [baseTrackEvent, user?.tenantId]
  );

  return {
    trackEvent,
  };
};
