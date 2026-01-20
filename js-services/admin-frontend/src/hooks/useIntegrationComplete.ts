import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCompletedDataSourcesCount } from '../utils/validation';
import { ConnectorStatus, useConnectorStatuses } from '../api/config';

/**
 * Get the correct redirect path after completing an integration
 * Returns '/' (home) if fewer than 3 integrations are complete, otherwise '/integrations'
 */
const getIntegrationRedirectPath = (connectorStatus: ConnectorStatus[] | undefined): string => {
  const completedCount = connectorStatus ? getCompletedDataSourcesCount(connectorStatus) : 0;
  return completedCount < 3 ? '/' : '/integrations';
};

/**
 * Custom hook that provides a callback for integration completion.
 * Automatically redirects to the home page if fewer than 3 integrations are complete,
 * otherwise redirects to the integrations page.
 *
 * @param onComplete - Optional callback to run before redirecting (e.g., analytics, side effects)
 * @returns A callback function to be used as the integration's onComplete handler
 *
 * @example
 * ```tsx
 * const handleComplete = useIntegrationComplete(() => {
 *   checkIfWeShouldStartAnsweringSampleQuestions();
 * });
 *
 * <NotionIntegration onComplete={handleComplete} />
 * ```
 */
export const useIntegrationComplete = (onComplete?: () => void): (() => void) => {
  const navigate = useNavigate();
  const { data: connectorStatuses } = useConnectorStatuses();

  return useCallback(() => {
    // Run the optional callback first (e.g., analytics)
    if (onComplete) {
      onComplete();
    }

    // Determine where to redirect based on integration count
    const redirectPath = getIntegrationRedirectPath(connectorStatuses);
    navigate(redirectPath);
  }, [onComplete, navigate, connectorStatuses]);
};
