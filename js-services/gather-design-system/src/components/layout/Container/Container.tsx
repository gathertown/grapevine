import React from 'react';

import { useLayoutComponentStyles } from '../layoutHooks';
import {
  ContainerSprinkles,
  containerSprinkles,
  FlexSprinkles,
  LayoutSprinkles,
} from '../layoutSprinkles.css';
import {
  AllFlexStyleProps,
  ContainerStyleProps,
  LayoutStyleProps,
  OverrideStyleProps,
  StyleProps,
} from '../layoutTypes';
import { containerStyleMap } from '../layoutUtils';

type VariableLayoutProps = Partial<
  LayoutStyleProps & AllFlexStyleProps & ContainerStyleProps & StyleProps
>;
type AtomicLayoutProps = Partial<ContainerSprinkles & FlexSprinkles & LayoutSprinkles>;

export type ContainerProps = VariableLayoutProps &
  AtomicLayoutProps & {
    children: React.ReactNode;
    as?: React.ElementType;
  } & Partial<OverrideStyleProps>;

export const Container = React.memo(
  React.forwardRef<HTMLElement, ContainerProps>(function Container(
    { children, style, as: Comp = 'div', ...layoutProps },
    ref
  ) {
    const { atomicStyles, variableStyles } = useLayoutComponentStyles<AtomicLayoutProps>({
      layoutProps,
      style,
      styleMap: containerStyleMap,
      getAtomicStyles: containerSprinkles,
    });

    return (
      <Comp ref={ref} className={atomicStyles} style={variableStyles}>
        {children}
      </Comp>
    );
  })
);
