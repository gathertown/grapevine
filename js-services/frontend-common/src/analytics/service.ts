import * as amplitude from '@amplitude/analytics-browser';
import { sessionReplayPlugin } from '@amplitude/plugin-session-replay-browser';
import { Identify } from '@amplitude/analytics-browser';
import posthog from 'posthog-js';
import type {
  AnalyticsEventName,
  AnalyticsEventProperties,
} from '@corporate-context/shared-common';
import { getConfig } from '../utils/config';

let isInitialized = false;
let amplitudeInitialized = false;
let posthogInitialized = false;

// GTM data layer helper - pushes events to Google Tag Manager
const pushToDataLayer = (eventName: string, eventProperties: object): void => {
  try {
    // Ensure dataLayer exists (GTM creates it, but we should be defensive)
    if (typeof window !== 'undefined') {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({
        event: eventName,
        ...eventProperties,
      });
    }
  } catch (error) {
    console.error('Failed to push event to GTM data layer:', error);
  }
};

export const initializeAnalytics = (): void => {
  const config = getConfig();
  const amplitudeApiKey = config.AMPLITUDE_API_KEY;
  const posthogApiKey = config.POSTHOG_API_KEY;
  const posthogHost = config.POSTHOG_HOST;
  const posthogUiHost = config.POSTHOG_UI_HOST;

  const hasAmplitudeKey = amplitudeApiKey && amplitudeApiKey.trim() !== '';
  const hasPosthogKey = posthogApiKey && posthogApiKey.trim() !== '';

  if (!hasAmplitudeKey && !hasPosthogKey) {
    console.warn('No analytics API keys found - Analytics tracking disabled');
    return;
  }

  if (isInitialized) {
    console.log('Analytics already initialized');
    return;
  }

  // Shared privacy configuration for consistent masking across providers
  const sensitiveSelectors = {
    // Elements to completely block from recording/tracking
    block: [
      '.amp-block',
      '[data-amp-block]',
      'input[type="password"]',
      'input[type="email"]',
      '.auth-form',
      '.sensitive-data',
    ],
    // Elements to mask/hide content but still track structure
    mask: ['.amp-mask', '[data-amp-mask]', '.user-info', '.token-display', '.api-key'],
  };

  // Initialize Amplitude if API key is provided
  if (hasAmplitudeKey && !amplitudeInitialized) {
    try {
      // Initialize Amplitude with basic configuration
      amplitude.init(amplitudeApiKey, undefined, {
        defaultTracking: {
          sessions: true,
          pageViews: true,
          formInteractions: false, // Disable for privacy
          fileDownloads: true,
        },
        trackingOptions: {
          ipAddress: false, // Don't track IP addresses for privacy
        },
      });

      // Configure and add Session Replay plugin
      const sessionReplayTracking = sessionReplayPlugin({
        sampleRate: 1.0, // 100% sample rate
        privacyConfig: {
          // Block elements with these selectors from being recorded
          blockSelector: sensitiveSelectors.block,
          // Mask text content in these elements
          maskSelector: sensitiveSelectors.mask,
        },
      });

      amplitude.add(sessionReplayTracking);
      amplitudeInitialized = true;
      console.log('Amplitude initialized successfully');
    } catch (error) {
      console.error('Failed to initialize Amplitude:', error);
    }
  }

  // Initialize PostHog if API key is provided
  if (hasPosthogKey && !posthogInitialized) {
    try {
      posthog.init(posthogApiKey, {
        api_host: posthogHost || 'https://us.i.posthog.com',
        ui_host: posthogUiHost || 'https://us.posthog.com',
        person_profiles: 'always',
      });

      posthogInitialized = true;
      console.log('PostHog initialized successfully');
    } catch (error) {
      console.error('Failed to initialize PostHog:', error);
    }
  }

  isInitialized = amplitudeInitialized || posthogInitialized;

  if (isInitialized) {
    console.log('Analytics initialized successfully');
  }
};

export const identify = (
  userId: string,
  userProperties?: Record<string, string | number | boolean | undefined>
): void => {
  if (!isInitialized) {
    return;
  }

  // Identify in Amplitude
  if (amplitudeInitialized) {
    try {
      // Set user ID
      amplitude.setUserId(userId);

      // Set user properties if provided
      if (userProperties) {
        const identify = new Identify();

        Object.entries(userProperties).forEach(([key, value]) => {
          if (value !== undefined) {
            identify.set(key, value);
          }
        });

        amplitude.identify(identify);
      }

      console.log('User identified in Amplitude:', userId, 'with properties:', userProperties);
    } catch (error) {
      console.error('Failed to identify user in Amplitude:', error);
    }
  }

  // Identify in PostHog
  if (posthogInitialized) {
    try {
      // PostHog identify function
      posthog.identify(userId, userProperties || {});

      console.log('User identified in PostHog:', userId, 'with properties:', userProperties);
    } catch (error) {
      console.error('Failed to identify user in PostHog:', error);
    }
  }
};

export const clearUser = (): void => {
  if (!isInitialized) {
    return;
  }

  // Clear user in Amplitude
  if (amplitudeInitialized) {
    try {
      amplitude.setUserId(undefined);
      console.log('User cleared from Amplitude');
    } catch (error) {
      console.error('Failed to clear user from Amplitude:', error);
    }
  }

  // Clear user in PostHog
  if (posthogInitialized) {
    try {
      posthog.reset();
      console.log('User cleared from PostHog');
    } catch (error) {
      console.error('Failed to clear user from PostHog:', error);
    }
  }
};

export const trackEvent = <T extends AnalyticsEventName>(
  eventName: T,
  eventProperties: AnalyticsEventProperties<T>
): void => {
  if (!isInitialized) {
    return;
  }

  // Track event in Amplitude
  if (amplitudeInitialized) {
    try {
      amplitude.track(eventName, eventProperties);
    } catch (error) {
      console.error('Failed to track event in Amplitude:', error);
    }
  }

  // Track event in PostHog
  if (posthogInitialized) {
    try {
      posthog.capture(eventName, eventProperties);
    } catch (error) {
      console.error('Failed to track event in PostHog:', error);
    }
  }

  // Push event to GTM data layer for all user-level events
  pushToDataLayer(eventName, eventProperties);
};

export const setUserProperty = (
  key: string,
  value: string | number | boolean | undefined
): void => {
  if (!isInitialized || value === undefined) {
    return;
  }

  // Set user property in Amplitude
  if (amplitudeInitialized) {
    try {
      const identify = new Identify();
      identify.set(key, value);
      amplitude.identify(identify);
    } catch (error) {
      console.error('Failed to set user property in Amplitude:', error);
    }
  }

  // Set user property in PostHog
  if (posthogInitialized) {
    try {
      posthog.setPersonProperties({ [key]: value });
    } catch (error) {
      console.error('Failed to set user property in PostHog:', error);
    }
  }
};
