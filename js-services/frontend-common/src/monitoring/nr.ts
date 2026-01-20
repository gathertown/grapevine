import { BrowserAgent } from '@newrelic/browser-agent/loaders/browser-agent';
import { getGrapevineEnv } from '../utils/environment';

// New Relic-specific types
export type NewRelicAttributes = Record<string, string | number | boolean | null>;

let isInitialized = false;
let browserAgent: BrowserAgent | null = null;

/**
 * Validates that required configuration values are present
 */
const areRequiredConfigsPresent = (
  config: Record<string, unknown>,
  requiredKeys: string[],
  serviceName: string
): boolean => {
  const missingKeys = requiredKeys.filter((key) => !config[key]);

  if (missingKeys.length > 0) {
    console.warn(
      `${serviceName}: Missing required configuration keys: ${missingKeys.join(', ')} - ${serviceName} disabled`
    );
    return false;
  }

  return true;
};

export const initializeNewRelic = (): void => {
  const config = {
    licenseKey: import.meta.env.VITE_NEW_RELIC_LICENSE_KEY,
    applicationId: import.meta.env.VITE_NEW_RELIC_APPLICATION_ID,
    accountId: import.meta.env.VITE_NEW_RELIC_ACCOUNT_ID,
    trustKey: import.meta.env.VITE_NEW_RELIC_TRUST_KEY,
    agentId: import.meta.env.VITE_NEW_RELIC_AGENT_ID,
  };

  // New Relic is enabled automatically when all required config is present
  if (
    !areRequiredConfigsPresent(
      config,
      ['licenseKey', 'applicationId', 'accountId', 'trustKey', 'agentId'],
      'New Relic'
    )
  ) {
    return;
  }

  if (isInitialized) {
    console.log('New Relic already initialized');
    return;
  }

  try {
    const environment = getGrapevineEnv();

    const options = {
      init: {
        distributed_tracing: { enabled: true },
        privacy: { cookies_enabled: false },
        ajax: { enabled: true, deny_list: [] },
        jserrors: { enabled: true },
        logging: { enabled: true, level: 'info' },
        metrics: { enabled: true },
        page_action: { enabled: true },
        page_view_event: { enabled: true },
        page_view_timing: { enabled: true },
        session_trace: { enabled: true },
        spa: { enabled: true },
      },
      info: {
        beacon: 'bam-cell.nr-data.net',
        errorBeacon: 'bam-cell.nr-data.net',
        licenseKey: config.licenseKey,
        applicationID: config.applicationId,
        sa: 1,
      },
      loader_config: {
        accountID: config.accountId,
        trustKey: config.trustKey,
        agentID: config.agentId,
        licenseKey: config.licenseKey,
        applicationID: config.applicationId,
      },
    };

    browserAgent = new BrowserAgent(options);

    // Set custom attributes for the environment
    browserAgent.setCustomAttribute('env', environment);
    browserAgent.setCustomAttribute('service', 'grapevine-admin-frontend');

    isInitialized = true;
    console.log(`New Relic initialized successfully for environment: ${environment}`);
  } catch (error) {
    console.error('Failed to initialize New Relic:', error);
  }
};

let _userProperties: NewRelicAttributes | null = null;
export const setUser = (userId: string, userProperties?: NewRelicAttributes): void => {
  if (!isInitialized || !browserAgent) {
    return;
  }

  const agent = browserAgent; // Capture reference to avoid null check issues

  // Set user ID as a custom attribute
  agent.setUserId(userId);

  // Set additional user properties
  if (userProperties) {
    // clone attributes in case they get mutated externally.
    // Shallow clone is sufficient because values are simple.
    _userProperties = { ...userProperties };
    Object.entries(userProperties).forEach(([key, value]) => {
      agent.setCustomAttribute(`user.${key}`, value);
    });
  }
};

export const clearUser = (): void => {
  if (!isInitialized || !browserAgent) {
    return;
  }

  browserAgent.setUserId(null);
  // Clear user-specific attributes by setting them to null
  if (_userProperties) {
    Object.keys(_userProperties).forEach((key) => {
      browserAgent?.setCustomAttribute(`user.${key}`, null);
    });
  }
  _userProperties = null;
};

export const addPageAction = (actionName: string, attributes: NewRelicAttributes = {}): void => {
  if (!isInitialized || !browserAgent) {
    return;
  }

  browserAgent.addPageAction(actionName, attributes);
};

export const noticeError = (error: Error): void => {
  if (!isInitialized || !browserAgent) {
    return;
  }

  browserAgent.noticeError(error);
  console.log('New Relic error recorded:', error.message);
};

export const setCustomAttribute = (key: string, value: string | number | boolean | null): void => {
  if (!isInitialized || !browserAgent) {
    return;
  }

  browserAgent.setCustomAttribute(key, value);
};

// Export as a single object with clean API
export const newrelic = {
  initialize: initializeNewRelic,
  setUser,
  clearUser,
  addPageAction,
  recordError: noticeError,
  setCustomAttribute,
};
