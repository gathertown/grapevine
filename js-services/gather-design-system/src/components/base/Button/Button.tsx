import React from 'react';

import { isNotNil, maybeReturnProps } from '../../../utils/fpHelpers';
import { Flex } from '../../layout/Flex/Flex';
import { Icon, IconName } from '../Icon/Icon';
import { Loader } from '../Loader/Loader';
import { Tooltip, TooltipProps } from '../Tooltip/Tooltip';
import { buttonContentRecipe, buttonRecipe, buttonTextStyle, ButtonVariants } from './Button.css';

type ButtonTooltip = string | Omit<TooltipProps, 'children'>;

export type ButtonProps = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'className'> &
  ButtonVariants & {
    children: React.ReactNode;
    loading?: boolean;
    loadingText?: string;
    leadingIcon?: IconName;
    trailingIcon?: IconName;
    tooltip?: ButtonTooltip;
    tooltipSide?: TooltipProps['side'];
    ref?: React.Ref<HTMLButtonElement>;
    dataTestId?: string;
  };

export const buttonIconSizeMap = {
  xs: 'xs',
  sm: 'sm',
  md: 'md',
  lg: 'lg',
} as const;

export const Button = React.memo(function Button({
  size,
  fullWidth,
  loading = false,
  loadingText,
  disabled,
  kind,
  children,
  leadingIcon,
  trailingIcon,
  iconOnly,
  tooltip,
  tooltipSide,
  ref,
  dataTestId,
  ...props
}: ButtonProps) {
  const iconSize = buttonIconSizeMap[size ?? 'md'];

  const button = (
    <button
      ref={ref}
      className={buttonRecipe({
        size,
        fullWidth,
        kind,
        iconOnly,
      })}
      disabled={disabled || loading}
      data-testid={dataTestId}
      // used to enable pointer events even if button is disabled in CSS
      // this way we can have tooltips on disabled buttons
      data-tooltip={tooltip ? '' : undefined}
      {...props}
    >
      <div className={buttonContentRecipe({ loading, fullWidth })}>
        {leadingIcon && <Icon name={leadingIcon} size={iconSize} />}
        <div className={buttonTextStyle}>{children}</div>
        {trailingIcon && <Icon name={trailingIcon} size={iconSize} />}
      </div>
      {loading && (
        <Flex position="absolute">
          <Loader />
          {isNotNil(loadingText) && <div className={buttonTextStyle}>{loadingText}</div>}
        </Flex>
      )}
    </button>
  );
  if (!tooltip) return button;

  const tooltipProps =
    typeof tooltip === 'string'
      ? { content: tooltip, ...maybeReturnProps(isNotNil(tooltipSide), { side: tooltipSide }) }
      : { ...tooltip, ...maybeReturnProps(isNotNil(tooltipSide), { side: tooltipSide }) };

  return <Tooltip {...tooltipProps}>{button}</Tooltip>;
});
