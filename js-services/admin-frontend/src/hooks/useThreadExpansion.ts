import { useState, useCallback } from 'react';
import type { ThreadDetails } from '../api/stats';
import { statsApi } from '../api/stats';

export interface UseThreadExpansionReturn {
  isExpanded: boolean;
  threadDetails: ThreadDetails | null;
  isLoading: boolean;
  error: string | null;
  handleExpandToggle: () => void;
}

export const useThreadExpansion = (messageId: string): UseThreadExpansionReturn => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [threadDetails, setThreadDetails] = useState<ThreadDetails | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExpandToggle = useCallback(async () => {
    if (!isExpanded && !threadDetails) {
      // Fetch thread details
      setIsLoading(true);
      setError(null);

      try {
        const details = await statsApi.getThreadDetails(messageId);
        setThreadDetails(details);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to load thread details';
        setError(errorMessage);
        console.error('Error loading thread details:', err);
      } finally {
        setIsLoading(false);
      }
    }

    setIsExpanded(!isExpanded);
  }, [isExpanded, threadDetails, messageId]);

  return {
    isExpanded,
    threadDetails,
    isLoading,
    error,
    handleExpandToggle,
  };
};
