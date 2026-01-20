import React from 'react';

import { Text } from '../Text/Text';
import { indicatorRecipe, IndicatorVariants } from './Indicator.css';

type IndicatorProps = IndicatorVariants & {
  count?: number;
};

export const Indicator = React.memo(function Indicator({ kind, count }: IndicatorProps) {
  if (count == null) return <div className={indicatorRecipe({ kind })} />;
  const trimmedCount = count > 99 ? '99+' : count;

  return (
    <div className={indicatorRecipe({ kind, withCount: true })}>
      <Text fontWeight="semibold" fontSize="xxs">
        {trimmedCount}
      </Text>
    </div>
  );
});
