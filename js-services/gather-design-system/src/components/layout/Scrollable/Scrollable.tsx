import React, { useRef } from 'react';

import { useLayoutComponentStyles } from '../layoutHooks';
import { LayoutSprinkles, layoutSprinkles } from '../layoutSprinkles.css';
import {
  FlexChildStyleProps,
  LayoutStyleProps,
  OverrideStyleProps,
  StyleProps,
} from '../layoutTypes';
import { baseStyleMap } from '../layoutUtils';
import { scrollContainerStyle } from './Scrollable.css';
import { Scrollbars } from './Scrollbars';

type VariableLayoutProps = Partial<LayoutStyleProps & FlexChildStyleProps & StyleProps>;
type AtomicLayoutProps = Partial<Omit<LayoutSprinkles, 'overflow' | 'overflowX' | 'overflowY'>>;

export type ScrollableProps = VariableLayoutProps &
  AtomicLayoutProps & {
    /**
     * Child content will go inside the scroll container.
     */
    children?: React.ReactNode;

    /**
     * A ref passed here will be forwarded to the scroll container (which, note, is not the top
     * level component within Scrollable).
     */
    ref?: React.RefObject<HTMLDivElement | null>;

    /**
     * Scroll direction: 'x' for horizontal, 'y' for vertical, 'both' for both directions.
     * Defaults to 'both'.
     */
    scrollDirection?: 'x' | 'y' | 'both';

    /**
     * Whether to automatically hide the scrollbars when the content is not scrollable.
     */
    autoHideScrollbars?: boolean;
  } & Partial<OverrideStyleProps>;

export const Scrollable = React.memo(function Scrollable({
  children,
  scrollDirection = 'both',
  style,
  ref,
  autoHideScrollbars,
  ...layoutProps
}: ScrollableProps) {
  const localScrollContainerRef = useRef<HTMLDivElement | null>(null);

  // Use the passed ref if available, otherwise use our local ref.
  const scrollContainerRef = ref ?? localScrollContainerRef;

  const { atomicStyles, variableStyles } = useLayoutComponentStyles<AtomicLayoutProps>({
    layoutProps,
    style: {
      ...style,
      position: 'relative',
      overflow: 'hidden',
      height: '100%',
      width: '100%',
    },
    styleMap: baseStyleMap,
    getAtomicStyles: layoutSprinkles,
  });

  return (
    <div className={atomicStyles} style={variableStyles}>
      <div
        ref={scrollContainerRef}
        className={scrollContainerStyle}
        style={{
          overflowX: scrollDirection === 'y' ? 'hidden' : 'auto',
          overflowY: scrollDirection === 'x' ? 'hidden' : 'auto',
        }}
      >
        {children}
      </div>

      <Scrollbars
        scrollContainerRef={scrollContainerRef}
        scrollDirection={scrollDirection}
        autoHide={autoHideScrollbars}
      />
    </div>
  );
});
