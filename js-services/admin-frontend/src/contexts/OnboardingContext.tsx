import { createContext, useContext, useMemo, memo } from 'react';
import type { FC, ReactNode } from 'react';
import type { TrialStatus } from '../types';
import { useUpload } from './UploadContext';
import { useBillingStatus } from '../hooks/useBillingStatus';
import { isSlackBotConfigured, getCompletedDataSourcesCount } from '../utils/validation';
import { TenantMode } from '@corporate-context/shared-common';
import { useApiKeys } from './ApiKeysContext';
import { useAllConfig, useConnectorStatuses } from '../api/config';

/**
 * QA Mode onboarding steps (Slack-focused)
 */
export interface QAOnboardingSteps {
  step1: boolean; // Set up Slack
  step2: boolean; // Upload Recent Slack Export
  step3: boolean; // Set up Integrations (3+ sources)
  step4: boolean; // Tell Grapevine about your Company
  step5: boolean; // Test Your Slack Bot
  step6: boolean; // Upload Historical Slack Export
}

/**
 * Dev Platform Mode onboarding steps (dev-focused)
 */
export interface DevPlatformOnboardingSteps {
  step1: boolean; // Connect Data Sources (1+ source)
  step2: boolean; // Tell Grapevine about your Company
  step3: boolean; // Set up API Key
}

export type OnboardingSteps = QAOnboardingSteps | DevPlatformOnboardingSteps;

/**
 * Shared onboarding data (no steps included)
 */
export interface OnboardingContextType {
  isInitialized: boolean;
  visibleStepsCount: number;
  incompleteVisibleStepsCount: number;
  billingComplete: boolean;
  trialStatus?: TrialStatus;
  tenantMode: TenantMode;
  qaSteps: QAOnboardingSteps;
  devPlatformSteps: DevPlatformOnboardingSteps;
}

/**
 * QA mode onboarding with steps
 */
export interface QAOnboardingContextType {
  steps: QAOnboardingSteps;
  isInitialized: boolean;
  visibleStepsCount: number;
  incompleteVisibleStepsCount: number;
  billingComplete: boolean;
  trialStatus?: TrialStatus;
  tenantMode: TenantMode;
}

/**
 * Dev Platform mode onboarding with steps
 */
export interface DevPlatformOnboardingContextType {
  steps: DevPlatformOnboardingSteps;
  isInitialized: boolean;
  visibleStepsCount: number;
  incompleteVisibleStepsCount: number;
  billingComplete: boolean;
  trialStatus?: TrialStatus;
  tenantMode: TenantMode;
}

const OnboardingContext = createContext<OnboardingContextType | null>(null);

interface OnboardingProviderProps {
  children: ReactNode;
}

export const OnboardingProvider: FC<OnboardingProviderProps> = memo(({ children }) => {
  const { data: configData } = useAllConfig();
  const { slackExports } = useUpload();
  const { billingStatus } = useBillingStatus();
  const { keys: apiKeys } = useApiKeys();

  const completedSources = useCompletedSourcesCount();

  // Determine tenant mode (default to dev_platform if not set)
  const tenantMode =
    configData?.TENANT_MODE === TenantMode.QA ? TenantMode.QA : TenantMode.DevPlatform;

  // Lazily calculate steps based on tenant mode - only calculate for active mode
  const { qaSteps, devPlatformSteps } = useMemo<{
    qaSteps: QAOnboardingSteps;
    devPlatformSteps: DevPlatformOnboardingSteps;
  }>(() => {
    const defaultQASteps: QAOnboardingSteps = {
      step1: false,
      step2: false,
      step3: false,
      step4: false,
      step5: false,
      step6: false,
    };

    const defaultDevPlatformSteps: DevPlatformOnboardingSteps = {
      step1: false,
      step2: false,
      step3: false,
    };

    if (!configData) {
      return {
        qaSteps: defaultQASteps,
        devPlatformSteps: defaultDevPlatformSteps,
      };
    }

    // Only calculate steps for the active tenant mode
    if (tenantMode === TenantMode.QA) {
      return {
        qaSteps: {
          step1: isSlackBotConfigured(configData), // Set up Slack
          step2: slackExports.length >= 1, // Upload Recent Slack Export
          step3: completedSources >= 3, // Set up Integrations (3+ sources)
          step4: !!(configData.COMPANY_CONTEXT && configData.COMPANY_CONTEXT.length >= 10), // Tell Grapevine about your Company
          step5: configData.SLACK_BOT_TESTED === 'true', // Test Your Slack Bot
          step6: slackExports.length >= 2, // Upload Historical Slack Export
        },
        devPlatformSteps: defaultDevPlatformSteps, // Not calculated for QA mode
      };
    }
    return {
      qaSteps: defaultQASteps, // Not calculated for dev platform mode
      devPlatformSteps: {
        step1: completedSources >= 1, // Connect Data Sources (1+ source)
        step2: !!(configData.COMPANY_CONTEXT && configData.COMPANY_CONTEXT.length >= 10), // Tell Grapevine about your Company
        step3: apiKeys.length > 0, // Set up API Key
      },
    };
  }, [configData, slackExports, completedSources, tenantMode, apiKeys]);

  // Calculate other derived values based on tenant mode
  const visibleSteps =
    tenantMode === TenantMode.DevPlatform
      ? [devPlatformSteps.step1, devPlatformSteps.step2, devPlatformSteps.step3]
      : [qaSteps.step1, qaSteps.step2, qaSteps.step3, qaSteps.step4, qaSteps.step5, qaSteps.step6];

  const incompleteVisibleStepsCount = visibleSteps.filter((step) => !step).length;
  const billingComplete = !!billingStatus?.subscription.hasActiveSubscription;
  const trialStatus = billingStatus?.trial;

  const isInitialized = !!configData;
  const contextValue = useMemo<OnboardingContextType>(
    () => ({
      isInitialized,
      visibleStepsCount: visibleSteps.length,
      incompleteVisibleStepsCount,
      billingComplete,
      trialStatus,
      tenantMode,
      qaSteps,
      devPlatformSteps,
    }),
    [
      isInitialized,
      visibleSteps.length,
      incompleteVisibleStepsCount,
      billingComplete,
      trialStatus,
      tenantMode,
      qaSteps,
      devPlatformSteps,
    ]
  );

  return <OnboardingContext.Provider value={contextValue}>{children}</OnboardingContext.Provider>;
});

OnboardingProvider.displayName = 'OnboardingProvider';

/**
 * Hook to access QA mode onboarding data
 * Only use this hook when you know the tenant is in QA mode
 */
export const useQAOnboarding = (): QAOnboardingContextType => {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useQAOnboarding must be used within an OnboardingProvider');
  }
  const { qaSteps, devPlatformSteps: _dev, ...shared } = context;
  return {
    ...shared,
    steps: qaSteps,
  };
};

/**
 * Hook to access Dev Platform mode onboarding data
 * Only use this hook when you know the tenant is in dev_platform mode
 */
export const useDevOnboarding = (): DevPlatformOnboardingContextType => {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useDevOnboarding must be used within an OnboardingProvider');
  }
  const { devPlatformSteps, qaSteps: _qa, ...shared } = context;
  return {
    ...shared,
    steps: devPlatformSteps,
  };
};

export const useOnboardingStepCount = () => {
  const devOnboarding = useDevOnboarding();
  const qaOnboarding = useQAOnboarding();

  return devOnboarding.tenantMode === TenantMode.DevPlatform
    ? {
        visibleStepsCount: devOnboarding.visibleStepsCount,
        incompleteVisibleStepsCount: devOnboarding.incompleteVisibleStepsCount,
        completedStepsCount:
          devOnboarding.visibleStepsCount - devOnboarding.incompleteVisibleStepsCount,
      }
    : {
        visibleStepsCount: qaOnboarding.visibleStepsCount,
        incompleteVisibleStepsCount: qaOnboarding.incompleteVisibleStepsCount,
        completedStepsCount:
          qaOnboarding.visibleStepsCount - qaOnboarding.incompleteVisibleStepsCount,
      };
};

export const useCompletedSourcesCount = () => {
  const { data: connectorStatuses } = useConnectorStatuses();
  return connectorStatuses ? getCompletedDataSourcesCount(connectorStatuses) : 0;
};

export { OnboardingContext };
