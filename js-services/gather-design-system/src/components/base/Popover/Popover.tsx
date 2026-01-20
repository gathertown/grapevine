import * as PopoverPrimitive from '@radix-ui/react-popover';
import classNames from 'classnames';
import React from 'react';

import { GatherDesignSystemColors } from '@gathertown/gather-design-foundations';
import { usePortalContainer } from '../../../helpers/usePortalContainer';
import { arrowFillStyles, backgroundColorStyles, contentRecipe } from './Popover.css';

export interface PopoverTriggerProps extends PopoverPrimitive.PopoverTriggerProps {}
export const PopoverTrigger = React.memo(
  React.forwardRef<HTMLButtonElement, PopoverTriggerProps>(function PopoverTrigger(
    { ...props },
    ref
  ) {
    return <PopoverPrimitive.Trigger asChild ref={ref} {...props} />;
  })
);
PopoverTrigger.displayName = 'Popover.Trigger';

type Side = PopoverPrimitive.PopoverContentProps['side'];
type Align = PopoverPrimitive.PopoverContentProps['align'];
type CollisionPadding = PopoverPrimitive.PopoverContentProps['collisionPadding'];

export interface PopoverContentProps {
  children: React.ReactNode;
  side?: Side;
  align?: Align;
  collisionPadding?: CollisionPadding;
  withArrow?: boolean;
  portalContainerId?: string;
  backgroundColor?: Extract<
    keyof GatherDesignSystemColors['bg'],
    'primary' | 'secondary' | 'primaryDark' | 'secondaryDark'
  >;
  noPadding?: boolean;
  noBoxShadow?: boolean;
  autoFocus?: boolean;
  onMouseEnter?: React.MouseEventHandler<HTMLDivElement>;
  onMouseLeave?: React.MouseEventHandler<HTMLDivElement>;
  closeOnClickOutside?: boolean;
}
export const PopoverContent = React.memo(
  React.forwardRef<HTMLDivElement, PopoverContentProps>(function PopoverContent(
    {
      children,
      withArrow = false,
      side = 'right',
      portalContainerId,
      backgroundColor = 'primary',
      noPadding = false,
      autoFocus = true,
      noBoxShadow = false,
      closeOnClickOutside = true,
      ...props
    },
    forwardedRef
  ) {
    const container = usePortalContainer(portalContainerId);

    return (
      <PopoverPrimitive.Portal container={container}>
        <PopoverPrimitive.Content
          ref={forwardedRef}
          className={classNames(
            contentRecipe({ noPadding, noBoxShadow }),
            backgroundColorStyles[backgroundColor]
          )}
          sideOffset={8}
          arrowPadding={10}
          side={side}
          onOpenAutoFocus={!autoFocus ? (e) => e.preventDefault() : undefined}
          onInteractOutside={!closeOnClickOutside ? (e) => e.preventDefault() : undefined}
          {...props}
        >
          {children}
          {withArrow && <PopoverPrimitive.Arrow className={arrowFillStyles[backgroundColor]} />}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    );
  })
);
PopoverContent.displayName = 'Popover.Content';

export interface PopoverProps extends PopoverPrimitive.PopoverProps {
  onOpenChange?: (open: boolean) => void;
}

const PopoverRoot = React.memo(function PopoverRoot({ ...props }: PopoverProps) {
  return <PopoverPrimitive.Root {...props} />;
});
PopoverRoot.displayName = 'Popover';

export const Popover = Object.assign(PopoverRoot, {
  Trigger: PopoverTrigger,
  Content: PopoverContent,
});
