import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import React from 'react';

import { usePortalContainer } from '../../../helpers/usePortalContainer';
import { Gothify } from '../../../providers/Gothify';
import { arrowFillStyle, tooltipStyle } from './Tooltip.css';

export type TooltipProps = {
  children?: React.ReactNode;
  content?: React.ReactNode;
  disabled?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  withArrow?: boolean;
  portalContainerId?: string;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  sideOffset?: number;
  delayDuration?: number;
};

// This prevents tooltips from colliding with the top drag handle in the desktop app. It would
// probably be more "correct" to pass this down through context rather than hardcoding it in the design
// system, but we don't use the design system anywhere else right now. In the future, we could consider
// passing this configuration through context if we have different collision padding needs in different
// contexts.
const TOP_COLLISION_PADDING = 24;

export const Tooltip = React.memo(
  React.forwardRef<HTMLDivElement, TooltipProps>(function Tooltip(
    {
      children,
      content,
      disabled,
      onOpenChange,
      open,
      withArrow = true,
      portalContainerId,
      side,
      align,
      sideOffset = 4,
      delayDuration = 200,
    },
    ref
  ) {
    const container = usePortalContainer(portalContainerId);

    return (
      <TooltipPrimitive.Provider delayDuration={delayDuration}>
        <TooltipPrimitive.Root
          disableHoverableContent
          open={!disabled && open}
          onOpenChange={onOpenChange}
        >
          <TooltipPrimitive.Trigger disabled={disabled} asChild>
            {/* TODO(ds): If a Tooltip user passes in a child that cannot accept an onClick prop, we should give dev a clear warning or error. */}
            {children}
          </TooltipPrimitive.Trigger>
          <TooltipPrimitive.Portal container={container}>
            <Gothify enabled>
              <TooltipPrimitive.Content
                ref={ref}
                className={tooltipStyle}
                sideOffset={sideOffset}
                arrowPadding={8}
                side={side}
                align={align}
                collisionPadding={{ top: TOP_COLLISION_PADDING }}
              >
                {content}
                {withArrow && <TooltipPrimitive.Arrow className={arrowFillStyle} />}
              </TooltipPrimitive.Content>
            </Gothify>
          </TooltipPrimitive.Portal>
        </TooltipPrimitive.Root>
      </TooltipPrimitive.Provider>
    );
  })
);
