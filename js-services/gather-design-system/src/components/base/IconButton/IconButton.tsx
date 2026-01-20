import React from 'react';

import { Button, buttonIconSizeMap, type ButtonProps } from '../Button/Button';
import { Icon, IconProps } from '../Icon/Icon';

export type IconButtonProps = Omit<ButtonProps, 'children'> & {
  icon: IconProps['name'];
  /**
   * @deprecated Use the button's 'kind' prop to control colors instead.
   * The button's color styling will automatically apply to the icon.
   */
  iconColor?: IconProps['color'];
  ref?: React.Ref<HTMLButtonElement>;
};

export const IconButton = React.memo(function IconButton({
  icon,
  iconColor,
  onClick,
  size = 'md',
  ref,
  ...buttonProps
}: IconButtonProps) {
  const iconSize = buttonIconSizeMap[size];
  return (
    <Button
      ref={ref}
      iconOnly
      size={size}
      {...buttonProps}
      onClick={
        onClick
          ? (ev) => {
              ev.stopPropagation();
              onClick(ev);
            }
          : undefined
      }
    >
      <Icon name={icon} size={iconSize} color={iconColor} />
    </Button>
  );
});
