import React from 'react';

import { tokens } from '@gathertown/gather-design-foundations';
import { appIndicatorClass } from './AppIndicator.css';

export const appIndicatorSizeMap = {
  xs: 6,
  sm: 8,
  md: 10,
  lg: 12,
  xl: 14,
} as const;

export type AppIndicatorProps = {
  src: string;
  alt: string;
  size?: keyof typeof appIndicatorSizeMap;
  ref?: React.Ref<HTMLImageElement>;
  style?: React.CSSProperties;
  name: string;
  onClick?: (e: React.MouseEvent<HTMLImageElement>) => void;
  onMouseUp?: (e: React.MouseEvent<HTMLImageElement>) => void;
};

export const AppIndicator = React.memo(function AppIndicator({
  size = 'md',
  alt,
  src,
  ref,
  ...props
}: {
  size?: keyof typeof appIndicatorSizeMap;
} & AppIndicatorProps) {
  return (
    <img
      {...props}
      ref={ref}
      src={src}
      alt={alt}
      className={appIndicatorClass}
      width={appIndicatorSizeMap[size]}
      height={appIndicatorSizeMap[size]}
      style={{ borderRadius: tokens.borderRadius[4], objectFit: 'cover', ...(props.style || {}) }}
    />
  );
});
