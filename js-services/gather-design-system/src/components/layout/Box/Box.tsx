import React from 'react';

import { useLayoutComponentStyles } from '../layoutHooks';
import { LayoutSprinkles, layoutSprinkles } from '../layoutSprinkles.css';
import {
  FlexChildStyleProps,
  LayoutStyleProps,
  OverrideStyleProps,
  StyleProps,
} from '../layoutTypes';
import { baseStyleMap } from '../layoutUtils';

type VariableLayoutProps = Partial<LayoutStyleProps & FlexChildStyleProps & StyleProps>;
type AtomicLayoutProps = Partial<LayoutSprinkles>;

export type BoxProps = VariableLayoutProps &
  AtomicLayoutProps & {
    children?: React.ReactNode;
    as?: React.ElementType;
    'data-testid'?: string;
  } & Partial<OverrideStyleProps>;

export const Box = React.memo(
  React.forwardRef<HTMLElement, BoxProps>(function Box(
    { children, style, as: Comp = 'div', 'data-testid': dataTestId, ...layoutProps },
    ref
  ) {
    const { atomicStyles, variableStyles } = useLayoutComponentStyles<AtomicLayoutProps>({
      layoutProps,
      style,
      styleMap: baseStyleMap,
      getAtomicStyles: layoutSprinkles,
    });

    return (
      <Comp ref={ref} className={atomicStyles} style={variableStyles} data-testid={dataTestId}>
        {children}
      </Comp>
    );
  })
);
