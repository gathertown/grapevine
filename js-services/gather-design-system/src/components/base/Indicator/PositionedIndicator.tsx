import React, { ComponentProps } from 'react';

import { Box } from '../../layout/Box/Box';
import { Flex } from '../../layout/Flex/Flex';
import { Indicator } from './Indicator';

type Props = {
  showEmpty?: boolean;
  count?: number;
  kind?: ComponentProps<typeof Indicator>['kind'];
  children: React.ReactNode;
};

export const PositionedIndicator = React.memo(function PositionedIndicator({
  showEmpty,
  count,
  kind,
  children,
}: Props) {
  const showIndicator = (count !== undefined && count > 0) || showEmpty;

  if (!showIndicator) return <>{children}</>;

  return (
    <Box position="relative">
      {children}
      <Flex right={-4} top={-4} position="absolute" pointerEvents="none">
        <Indicator count={count} kind={kind} />
      </Flex>
    </Box>
  );
});
