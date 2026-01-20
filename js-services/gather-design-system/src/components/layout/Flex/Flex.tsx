import React from 'react';

import { useLayoutComponentStyles } from '../layoutHooks';
import { FlexSprinkles, flexSprinkles } from '../layoutSprinkles.css';
import {
  AllFlexStyleProps,
  LayoutStyleProps,
  OverrideStyleProps,
  StyleProps,
} from '../layoutTypes';
import { baseStyleMap } from '../layoutUtils';

type VariableLayoutProps = Partial<LayoutStyleProps & AllFlexStyleProps & StyleProps>;
type AtomicLayoutProps = Partial<FlexSprinkles>;

export type FlexProps = VariableLayoutProps &
  AtomicLayoutProps & {
    children?: React.ReactNode;
    as?: React.ElementType;
    tabIndex?: number;
    'data-testid'?: string;
  } & Partial<OverrideStyleProps>;

const defaultProps: Partial<FlexProps> = {
  display: 'flex',
};

export const Flex = React.memo(
  React.forwardRef<HTMLElement, FlexProps>(function Flex(
    { children, style, tabIndex, as: Comp = 'div', 'data-testid': dataTestId, ...layoutProps },
    ref
  ) {
    const { atomicStyles, variableStyles } = useLayoutComponentStyles<AtomicLayoutProps>({
      defaultProps,
      layoutProps,
      style,
      styleMap: baseStyleMap,
      getAtomicStyles: flexSprinkles,
    });

    return (
      <Comp
        ref={ref}
        className={atomicStyles}
        style={variableStyles}
        tabIndex={tabIndex}
        data-testid={dataTestId}
      >
        {children}
      </Comp>
    );
  })
);
