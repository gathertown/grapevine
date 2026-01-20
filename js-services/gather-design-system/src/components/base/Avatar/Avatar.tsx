import classNames from 'classnames';
import React, { useState } from 'react';

import { doIt } from '../../../utils/fpHelpers';
import { theme, tokens } from '@gathertown/gather-design-foundations';
import { Box } from '../../layout/Box/Box';
import { AppIndicator, AppIndicatorProps } from '../AppIndicator/AppIndicator';
import {
  StatusIndicator,
  StatusIndicatorKind,
  statusIndicatorSizeMap,
} from '../Status/StatusIndicator';
import { Tooltip, TooltipProps } from '../Tooltip/Tooltip';
import {
  avatarBorderRecipe,
  avatarClipPathRecipe,
  avatarImageStyle,
  avatarRecipe,
  avatarStatusDotSizeMap,
  AvatarVariants,
  borderRadiusStyles,
} from './Avatar.css';

type AvatarTooltip = string | Omit<TooltipProps, 'children'>;

export type AvatarProps = AvatarVariants & {
  alt?: string;
  name?: string; // TODO APP-8715
  src?: string;
  status?: StatusIndicatorKind | React.ReactElement<{ size: keyof typeof statusIndicatorSizeMap }>;
  tooltip?: AvatarTooltip;
  shape?: 'circle' | 'square';
  fluid?: boolean;
  showStatusOutline?: boolean;
  app?:
    | Omit<AppIndicatorProps, 'size'>
    | React.ReactElement<{ size: keyof typeof statusIndicatorSizeMap }>;
};

export const Avatar: React.FC<AvatarProps> = React.memo(function Avatar({
  alt,
  name,
  size = 'md',
  src,
  status,
  tooltip,
  shape = 'circle',
  fluid,
  showStatusOutline,
  app,
}) {
  const [hasError, setHasError] = useState(false);

  const { statusSize } = avatarStatusDotSizeMap[size];

  const placeholderColors = Object.values(theme.placeholderPalette);

  // Deterministic means of mapping name to color index
  // This is a simple hash function that converts a string to an index
  const hashStringToIndex = (str: string, arrayLength: number): number => {
    if (!str) return 0;

    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash = hash & hash; // Convert to 32-bit integer
    }
    // Ensure positive index and proper distribution
    return Math.abs(hash) % arrayLength;
  };

  const placeholderFill =
    placeholderColors[hashStringToIndex(name ?? '', placeholderColors.length)];

  const clipStatus = doIt(() => {
    if (typeof status === 'string' || typeof status === 'undefined') return status;

    return 'custom';
  });

  const avatar = (
    <div className={avatarRecipe({ size, fluid })}>
      <div
        className={avatarClipPathRecipe({
          size,
          status: clipStatus,
          app: !!app,
          showStatusOutline,
        })}
        style={{
          width: '100%',
          height: '100%',
        }}
      >
        {src && !hasError ? (
          <img
            src={src}
            alt={alt ?? name}
            className={classNames(avatarImageStyle, borderRadiusStyles[shape])}
            onError={() => setHasError(true)}
          />
        ) : (
          <svg
            viewBox="0 0 24 24"
            aria-label={name}
            className={classNames(avatarImageStyle, borderRadiusStyles[shape])}
          >
            <rect x="0" y="0" width="24" height="24" fill={placeholderFill} />

            <text
              x="50%"
              y="50%"
              textAnchor="middle"
              dominantBaseline="central"
              fill={theme.dangerouslyStatic.alphaBlack60}
              fontWeight={tokens.fontWeight.bold}
              fontSize={status ? 11 : 14} // Relative size to viewBox; actual size is fluid
            >
              {name?.slice(0, 1).toUpperCase()}
            </text>
          </svg>
        )}
        <div
          className={classNames(
            avatarBorderRecipe({ size: status ? size : undefined }),
            borderRadiusStyles[shape]
          )}
        />
      </div>
      {app && (
        <Box position="absolute" right={0} top={0}>
          {React.isValidElement(app) ? (
            React.cloneElement(app, { size: statusSize })
          ) : (
            <AppIndicator {...app} size={statusSize} />
          )}
        </Box>
      )}

      {status && (
        <Box position="absolute" right={0} bottom={0}>
          {typeof status === 'string' ? (
            <StatusIndicator kind={status} size={statusSize} />
          ) : (
            React.cloneElement(status, { size: statusSize })
          )}
        </Box>
      )}
    </div>
  );

  if (!tooltip) return avatar;
  const tooltipProps = typeof tooltip === 'string' ? { content: tooltip } : tooltip;

  return <Tooltip {...tooltipProps}>{avatar}</Tooltip>;
});
