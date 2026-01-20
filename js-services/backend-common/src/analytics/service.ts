import { NodeClient } from '@amplitude/node';
import { PostHog } from 'posthog-node';
import { AnalyticsEventName, AnalyticsEventProperties } from '@corporate-context/shared-common';
import { logger } from '../logger';

/**
 * Backend analytics service for tracking events across backend services
 */
export class BackendAnalyticsService {
  private amplitudeClient: NodeClient | null = null;
  private posthogClient: PostHog | null = null;
  private _isInitialized = false;

  /**
   * Check if the service is initialized
   */
  public get isInitialized(): boolean {
    return this._isInitialized;
  }

  constructor(amplitudeApiKey?: string, posthogApiKey?: string, posthogHost?: string) {
    if (amplitudeApiKey || posthogApiKey) {
      this.initialize(amplitudeApiKey, posthogApiKey, posthogHost);
    } else {
      logger.warn('[Analytics] No API keys provided, skipping initialization', {
        operation: 'analytics-initialize',
      });
    }
  }

  /**
   * Initialize analytics clients with API keys
   */
  public initialize(amplitudeApiKey?: string, posthogApiKey?: string, posthogHost?: string): void {
    if (this.isInitialized) {
      return;
    }

    // Initialize Amplitude client if API key provided
    if (amplitudeApiKey) {
      try {
        this.amplitudeClient = new NodeClient(amplitudeApiKey, {
          maxCachedEvents: 50,
          uploadIntervalInSec: 10,
        });
        logger.debug('[Analytics] Amplitude client initialized', {
          operation: 'analytics-initialize',
        });
      } catch (error) {
        logger.error('[Analytics] Error initializing Amplitude client:', {
          error,
          operation: 'analytics-initialize',
        });
      }
    }

    // Initialize PostHog client if API key provided
    if (posthogApiKey) {
      try {
        this.posthogClient = new PostHog(posthogApiKey, {
          host: posthogHost || 'https://us.i.posthog.com',
          flushAt: 50,
          flushInterval: 10000,
        });
        logger.debug('[Analytics] PostHog client initialized', {
          operation: 'analytics-initialize',
        });
      } catch (error) {
        logger.error('[Analytics] Error initializing PostHog client:', {
          error,
          operation: 'analytics-initialize',
        });
      }
    }

    this._isInitialized = true;
  }

  /**
   * Identify a user with their properties
   */
  public async identify(userId: string, userProperties: Record<string, unknown>): Promise<void> {
    if (!this._isInitialized) {
      logger.warn('[Analytics] Service not initialized, skipping identify:', {
        userId,
        operation: 'analytics-identify',
      });
      return;
    }

    const promises: Promise<void>[] = [];

    // Identify in Amplitude
    if (this.amplitudeClient) {
      promises.push(
        (async () => {
          try {
            const sessionId = Date.now();
            const identifyEvent = {
              event_type: '$identify',
              user_id: userId,
              device_id: userId,
              session_id: sessionId,
              user_properties: {
                ...userProperties,
                timestamp: new Date().toISOString(),
                source: 'backend',
              },
            };

            logger.debug('[Analytics] Identifying user in Amplitude:', {
              userId,
              identifyEvent,
              userProperties,
              operation: 'analytics-identify',
            });

            if (this.amplitudeClient) {
              await this.amplitudeClient.logEvent(identifyEvent);
            }
          } catch (error) {
            logger.error('[Analytics] Error identifying user in Amplitude:', {
              userId,
              error,
              operation: 'analytics-identify',
            });
          }
        })()
      );
    }

    // Identify in PostHog
    if (this.posthogClient) {
      promises.push(
        (async () => {
          try {
            logger.debug('[Analytics] Identifying user in PostHog:', {
              userId,
              userProperties,
              operation: 'analytics-identify',
            });

            if (this.posthogClient) {
              this.posthogClient.identify({
                distinctId: userId,
                properties: {
                  ...userProperties,
                  timestamp: new Date().toISOString(),
                  source: 'backend',
                },
              });
            }
          } catch (error) {
            logger.error('[Analytics] Error identifying user in PostHog:', {
              userId,
              error,
              operation: 'analytics-identify',
            });
          }
        })()
      );
    }

    // Execute all identify operations in parallel
    if (promises.length > 0) {
      try {
        await Promise.allSettled(promises);
      } catch (error) {
        logger.error('[Analytics] Error in parallel identify operations:', {
          userId,
          error,
          operation: 'analytics-identify',
        });
      }
    }
  }

  /**
   * Track an event with tenant and user context
   */
  public async trackEvent<T extends AnalyticsEventName>(
    eventName: T,
    properties: AnalyticsEventProperties<T>
  ): Promise<void> {
    if (!this._isInitialized) {
      logger.warn('[Analytics] Service not initialized, skipping event:', {
        eventName,
        operation: 'analytics-track-event',
      });
      return;
    }

    const promises: Promise<void>[] = [];
    const userId = properties.tenant_id || 'unknown-tenant';

    // Track event in Amplitude
    if (this.amplitudeClient) {
      promises.push(
        (async () => {
          try {
            const sessionId = Date.now();
            const event = {
              event_type: eventName,
              user_id: userId,
              device_id: userId,
              session_id: sessionId,
              event_properties: {
                ...properties,
                timestamp: new Date().toISOString(),
                source: 'backend',
              },
            };

            logger.debug('[Analytics] Tracking event in Amplitude:', {
              eventName,
              event,
              properties,
              operation: 'analytics-track-event',
            });

            if (this.amplitudeClient) {
              await this.amplitudeClient.logEvent(event);
            }
          } catch (error) {
            logger.error('[Analytics] Error tracking event in Amplitude:', {
              eventName,
              error,
              operation: 'analytics-track-event',
            });
          }
        })()
      );
    }

    // Track event in PostHog
    if (this.posthogClient) {
      promises.push(
        (async () => {
          try {
            logger.debug('[Analytics] Tracking event in PostHog:', {
              eventName,
              properties,
              operation: 'analytics-track-event',
            });

            if (this.posthogClient) {
              this.posthogClient.capture({
                distinctId: userId,
                event: eventName,
                properties: {
                  ...properties,
                  timestamp: new Date().toISOString(),
                  source: 'backend',
                },
              });
            }
          } catch (error) {
            logger.error('[Analytics] Error tracking event in PostHog:', {
              eventName,
              error,
              operation: 'analytics-track-event',
            });
          }
        })()
      );
    }

    // Execute all tracking operations in parallel
    if (promises.length > 0) {
      try {
        await Promise.allSettled(promises);
      } catch (error) {
        logger.error('[Analytics] Error in parallel track operations:', {
          eventName,
          error,
          operation: 'analytics-track-event',
        });
      }
    }
  }

  /**
   * Track an event ONLY in Amplitude (skips PostHog)
   * Use this for events that should not be sent to PostHog
   */
  public async trackEventAmplitudeOnly<T extends AnalyticsEventName>(
    eventName: T,
    properties: AnalyticsEventProperties<T>
  ): Promise<void> {
    if (!this._isInitialized) {
      logger.warn('[Analytics] Service not initialized, skipping event:', {
        eventName,
        operation: 'analytics-track-event-amplitude-only',
      });
      return;
    }

    // Track event in Amplitude only
    if (this.amplitudeClient) {
      try {
        const userId = properties.tenant_id || 'unknown-tenant';
        const sessionId = Date.now();
        const event = {
          event_type: eventName,
          user_id: userId,
          device_id: userId,
          session_id: sessionId,
          event_properties: {
            ...properties,
            timestamp: new Date().toISOString(),
            source: 'backend',
          },
        };

        logger.debug('[Analytics] Tracking event in Amplitude only:', {
          eventName,
          event,
          properties,
          operation: 'analytics-track-event-amplitude-only',
        });

        await this.amplitudeClient.logEvent(event);
      } catch (error) {
        logger.error('[Analytics] Error tracking event in Amplitude:', {
          eventName,
          error,
          operation: 'analytics-track-event-amplitude-only',
        });
      }
    } else {
      logger.warn('[Analytics] Amplitude client not initialized, skipping event:', {
        eventName,
        operation: 'analytics-track-event-amplitude-only',
      });
    }
  }

  /**
   * Flush pending events
   */
  public async flush(): Promise<void> {
    if (!this._isInitialized) {
      return;
    }

    const promises: Promise<void>[] = [];

    // Flush Amplitude client
    if (this.amplitudeClient) {
      promises.push(
        (async () => {
          try {
            if (this.amplitudeClient) {
              await this.amplitudeClient.flush();
            }
          } catch (error) {
            logger.error('[Analytics] Error flushing Amplitude events:', {
              error,
              operation: 'analytics-flush',
            });
          }
        })()
      );
    }

    // Flush PostHog client
    if (this.posthogClient) {
      promises.push(
        (async () => {
          try {
            if (this.posthogClient) {
              await this.posthogClient.flush();
            }
          } catch (error) {
            logger.error('[Analytics] Error flushing PostHog events:', {
              error,
              operation: 'analytics-flush',
            });
          }
        })()
      );
    }

    // Execute all flush operations in parallel
    if (promises.length > 0) {
      try {
        await Promise.allSettled(promises);
      } catch (error) {
        logger.error('[Analytics] Error in parallel flush operations:', {
          error,
          operation: 'analytics-flush',
        });
      }
    }
  }

  /**
   * Shutdown the analytics clients
   */
  public async shutdown(): Promise<void> {
    if (!this._isInitialized) {
      return;
    }

    try {
      // Flush all pending events first
      await this.flush();

      // Clean up clients
      if (this.posthogClient) {
        try {
          await this.posthogClient.shutdown();
        } catch (error) {
          logger.error('[Analytics] Error shutting down PostHog client:', {
            error,
            operation: 'analytics-shutdown',
          });
        }
      }

      this.amplitudeClient = null;
      this.posthogClient = null;
      this._isInitialized = false;
    } catch (error) {
      logger.error('[Analytics] Error shutting down analytics service:', {
        error,
        operation: 'analytics-shutdown',
      });
    }
  }
}

// Singleton instance for reuse across the application
let analyticsService: BackendAnalyticsService | null = null;

/**
 * Get the global analytics service instance
 * @param amplitudeApiKey Optional Amplitude API key override. If not provided, will use VITE_AMPLITUDE_API_KEY env var
 * @param posthogApiKey Optional PostHog API key override. If not provided, will use VITE_POSTHOG_API_KEY env var
 * @param posthogHost Optional PostHog host override. If not provided, will use VITE_POSTHOG_HOST env var
 */
export function getAnalyticsService(
  amplitudeApiKey?: string,
  posthogApiKey?: string,
  posthogHost?: string
): BackendAnalyticsService {
  if (analyticsService?.isInitialized) {
    return analyticsService;
  }

  if (!amplitudeApiKey) {
    amplitudeApiKey = process.env.VITE_AMPLITUDE_API_KEY;
  }

  if (!posthogApiKey) {
    posthogApiKey = process.env.VITE_POSTHOG_API_KEY;
  }

  if (!posthogHost) {
    posthogHost = process.env.VITE_POSTHOG_HOST;
  }

  analyticsService = new BackendAnalyticsService(amplitudeApiKey, posthogApiKey, posthogHost);

  return analyticsService;
}
