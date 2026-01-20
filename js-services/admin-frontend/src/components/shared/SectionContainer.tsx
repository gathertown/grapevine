import type { ReactNode, FC } from 'react';
import { Box } from '@gathertown/gather-design-system';

interface SectionContainerProps {
  isComplete?: boolean;
  children: ReactNode;
}

export const SectionContainer: FC<SectionContainerProps> = ({ isComplete = false, children }) => {
  return (
    <Box
      borderColor={isComplete ? 'successPrimary' : 'tertiary'}
      borderRadius={8}
      p={16}
      borderWidth={1}
      borderStyle="solid"
      style={{
        backgroundColor: isComplete ? '#f7fef7' : 'transparent',
        transition: 'all 0.2s ease-in-out',
      }}
    >
      {children}
    </Box>
  );
};
