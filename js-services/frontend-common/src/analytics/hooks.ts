import { useCallback } from 'react';
import type {
  AnalyticsEventName,
  AnalyticsEventProperties,
} from '@corporate-context/shared-common';
import { initializeAnalytics, identify, clearUser, trackEvent, setUserProperty } from './service';
import { getGrapevineEnv } from '../utils/environment';
import { getConfig } from '../utils/config';

export interface UseAnalyticsReturn {
  initialize: () => void;
  identify: (
    userId: string,
    userProperties?: Record<string, string | number | boolean | undefined>
  ) => void;
  clearUser: () => void;
  trackEvent: <T extends AnalyticsEventName>(
    eventName: T,
    eventProperties: AnalyticsEventProperties<T>
  ) => void;
  setUserProperty: (key: string, value: string | number | boolean | undefined) => void;
  isEnabled: boolean;
  environment: string;
}

export const useAnalytics = (): UseAnalyticsReturn => {
  const initialize = useCallback(() => {
    initializeAnalytics();
  }, []);

  const identifyCallback = useCallback(
    (userId: string, userProperties?: Record<string, string | number | boolean | undefined>) => {
      identify(userId, userProperties);
    },
    []
  );

  const clearUserCallback = useCallback(() => {
    clearUser();
  }, []);

  const trackEventCallback = useCallback(
    <T extends AnalyticsEventName>(eventName: T, eventProperties: AnalyticsEventProperties<T>) => {
      trackEvent(eventName, eventProperties);
    },
    []
  );

  const setUserPropertyCallback = useCallback(
    (key: string, value: string | number | boolean | undefined) => {
      setUserProperty(key, value);
    },
    []
  );

  const config = getConfig();

  return {
    initialize,
    identify: identifyCallback,
    clearUser: clearUserCallback,
    trackEvent: trackEventCallback,
    setUserProperty: setUserPropertyCallback,
    isEnabled: !!(config.AMPLITUDE_API_KEY || config.POSTHOG_API_KEY),
    environment: getGrapevineEnv(),
  };
};
