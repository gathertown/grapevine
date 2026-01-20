import classNames from 'classnames';
import React from 'react';

import { isNotNilAndNotEmpty } from '../../../utils/fpHelpers';
import { Icon, IconProps } from '../Icon/Icon';
import { badgeRecipe, badgeTextStyle, BadgeVariants } from './Badge.css';

const badgeSizeToIconSizeMap = {
  sm: 'xxs',
  md: 'xs',
  'sm-square': 'xxs',
} as const;

export type BadgeProps = {
  text?: string | number;
  color?: NonNullable<BadgeVariants>['color'];
  kind?: 'fill' | 'outline';
  size?: 'sm' | 'md' | 'sm-square';
  icon?: IconProps['name'];
  dataTestId?: string;
};

export const Badge: React.FC<BadgeProps> = React.memo(function Badge({
  text,
  kind = 'fill',
  size = 'md',
  color = 'gray',
  icon,
  dataTestId,
}) {
  const showIcon = (size === 'md' || size === 'sm-square') && isNotNilAndNotEmpty(icon);
  return (
    <span className={classNames(badgeRecipe({ kind, size, color }))} data-testid={dataTestId}>
      {showIcon && <Icon name={icon} size={badgeSizeToIconSizeMap[size]} />}
      {text && <span className={badgeTextStyle}>{text}</span>}
    </span>
  );
});
