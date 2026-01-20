import React from 'react';

import { Tooltip, TooltipProps } from '../Tooltip/Tooltip';
import { clickableStyle } from './Clickable.css';

type ButtonTooltip = string | Omit<TooltipProps, 'children'>;

type ClickableProps = Pick<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  | 'disabled'
  | 'onClick'
  | 'className'
  | 'aria-label'
  | 'style'
  | 'tabIndex'
  | 'onMouseEnter'
  | 'onMouseLeave'
  | 'type'
> & {
  tooltip?: ButtonTooltip;
};

export const Clickable = React.memo(
  React.forwardRef<HTMLButtonElement, React.PropsWithChildren<ClickableProps>>(function Clickable(
    { children, className, tooltip, ...props },
    ref
  ) {
    const button = (
      <button ref={ref} className={`${clickableStyle} ${className}`} {...props}>
        {children}
      </button>
    );

    if (!tooltip) return button;

    const tooltipProps = typeof tooltip === 'string' ? { content: tooltip } : tooltip;

    return <Tooltip {...tooltipProps}>{button}</Tooltip>;
  })
);
