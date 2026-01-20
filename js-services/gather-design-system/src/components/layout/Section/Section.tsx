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
  LayoutStyleProps,
  OverrideStyleProps,
  SectionStyleProps,
  StyleProps,
} from '../layoutTypes';
import { sectionStyleMap } from '../layoutUtils';

type VariableLayoutProps = Partial<
  LayoutStyleProps & AllFlexStyleProps & SectionStyleProps & StyleProps
>;
type AtomicLayoutProps = Partial<ContainerSprinkles & FlexSprinkles & LayoutSprinkles>;

export type SectionProps = VariableLayoutProps &
  AtomicLayoutProps & {
    children: React.ReactNode;
    as?: React.ElementType;
  } & Partial<OverrideStyleProps>;

export const Section = React.memo(
  React.forwardRef<HTMLElement, SectionProps>(function Section(
    { children, style, ...layoutProps },
    ref
  ) {
    const Comp = layoutProps.as || 'section';

    const { atomicStyles, variableStyles } = useLayoutComponentStyles<AtomicLayoutProps>({
      layoutProps,
      style,
      styleMap: sectionStyleMap,
      getAtomicStyles: containerSprinkles,
    });

    return (
      <Comp ref={ref} className={atomicStyles} style={variableStyles}>
        {children}
      </Comp>
    );
  })
);
