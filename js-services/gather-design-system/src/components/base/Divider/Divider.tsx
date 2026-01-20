import classNames from 'classnames';
import React from 'react';

import { GatherDesignSystemColors } from '@gathertown/gather-design-foundations';
import { colorStyle, horizontalStyle, verticalStyle } from './Divider.css';

export type DividerProps = {
  direction: 'horizontal' | 'vertical';
  color?: keyof GatherDesignSystemColors['border'];
};

export const Divider = React.memo(
  React.forwardRef<HTMLDivElement, DividerProps>(function Divider(
    { direction, color = 'tertiary' },
    ref
  ) {
    return (
      <div
        ref={ref}
        className={classNames(colorStyle[color], {
          [horizontalStyle]: direction === 'horizontal',
          [verticalStyle]: direction === 'vertical',
        })}
      />
    );
  })
);
