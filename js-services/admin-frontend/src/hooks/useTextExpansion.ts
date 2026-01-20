import { useState, useCallback } from 'react';

export interface UseTextExpansionReturn {
  isTextExpanded: boolean;
  handleTextExpandToggle: () => void;
}

export const useTextExpansion = (): UseTextExpansionReturn => {
  const [isTextExpanded, setIsTextExpanded] = useState(false);

  const handleTextExpandToggle = useCallback(() => {
    setIsTextExpanded(!isTextExpanded);
  }, [isTextExpanded]);

  return {
    isTextExpanded,
    handleTextExpandToggle,
  };
};
