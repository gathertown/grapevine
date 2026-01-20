import { useState, useEffect, useCallback, useRef } from 'react';
import { billingApi } from '../api/billing';
import type { BillingStatusResponse } from '../types';
import { ApiError } from '../api/client';

export interface UseBillingStatusReturn {
  billingStatus: BillingStatusResponse | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  pollUntilChange: (
    expectedChange: (status: BillingStatusResponse) => boolean,
    timeout?: number
  ) => Promise<boolean>;
}

export const useBillingStatus = (): UseBillingStatusReturn => {
  const [billingStatus, setBillingStatus] = useState<BillingStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchBillingStatus = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const status = await billingApi.getStatus();
      setBillingStatus(status);
    } catch (err) {
      const errorMessage = err instanceof ApiError ? err.message : 'Failed to fetch billing status';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const pollUntilChange = useCallback(
    async (
      expectedChange: (status: BillingStatusResponse) => boolean,
      timeout: number = 15000 // 15 seconds default
    ): Promise<boolean> => {
      const startTime = Date.now();
      const pollInterval = 1500; // 1.5 seconds

      return new Promise((resolve) => {
        const poll = async () => {
          try {
            const status = await billingApi.getStatus();
            setBillingStatus(status);

            if (expectedChange(status)) {
              resolve(true);
              return;
            }

            if (Date.now() - startTime >= timeout) {
              resolve(false);
              return;
            }

            pollTimeoutRef.current = setTimeout(poll, pollInterval);
          } catch {
            // Continue polling even if individual requests fail
            if (Date.now() - startTime >= timeout) {
              resolve(false);
              return;
            }
            pollTimeoutRef.current = setTimeout(poll, pollInterval);
          }
        };

        poll();
      });
    },
    []
  );

  useEffect(() => {
    fetchBillingStatus();

    // Cleanup polling on unmount
    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
      }
    };
  }, [fetchBillingStatus]);

  // Check for return from Stripe portal and poll for changes
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('from') === 'stripe-portal') {
      // Coming back from Stripe portal - poll for changes
      setTimeout(() => {
        pollUntilChange((_status) => true, 10000); // Poll for 10 seconds to pick up any changes
      }, 1000);

      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [pollUntilChange]);

  return {
    billingStatus,
    isLoading,
    error,
    refetch: fetchBillingStatus,
    pollUntilChange,
  };
};
