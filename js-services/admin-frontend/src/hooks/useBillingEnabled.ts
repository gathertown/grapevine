import { useQuery } from '@tanstack/react-query';
import { billingApi } from '../api/billing';

/**
 * Hook to check if billing is enabled on this deployment.
 * Used to conditionally show/hide billing UI elements.
 */
export const useBillingEnabled = () => {
  const query = useQuery({
    queryKey: ['billing-enabled'],
    queryFn: () => billingApi.isEnabled(),
    staleTime: Infinity, // This won't change during a session
    gcTime: Infinity,
    retry: false,
  });

  return {
    isBillingEnabled: query.data?.enabled ?? false,
    isLoading: query.isLoading,
    error: query.error,
  };
};
