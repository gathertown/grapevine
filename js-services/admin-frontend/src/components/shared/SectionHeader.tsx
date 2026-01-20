import type { FC } from 'react';
import { Box, Text } from '@gathertown/gather-design-system';

interface SectionHeaderProps {
  title: string;
  isComplete?: boolean;
}

export const SectionHeader: FC<SectionHeaderProps> = ({ title }) => {
  return (
    <Box py={8} mb={4}>
      <Text fontSize="xs" color="tertiary" textTransform="uppercase" fontWeight="semibold">
        {title}
      </Text>
    </Box>
  );
};
