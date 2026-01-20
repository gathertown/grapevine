import React from 'react';

import { GatherDesignSystemColors, theme } from '@gathertown/gather-design-foundations';
import * as iconComponents from './generated';
import { iconRecipe, iconStyle, IconVariants } from './Icon.css';

export type IconName = Uncapitalize<keyof typeof iconComponents>;

type IconColors = Extract<
  | keyof GatherDesignSystemColors['text']
  | keyof GatherDesignSystemColors['presence']
  | keyof GatherDesignSystemColors['eventStatus']
  | keyof GatherDesignSystemColors['fg'],
  string
>;

export type IconProps = IconVariants & {
  name: IconName;
  color?: IconColors;
  fill?: string;
};

/**
 * HELLO! Are you looking to add new icons to this component? If so, please take a look at the
 * README.md in the `gather-design-system` module.
 */

const iconsMap = {
  ...Object.fromEntries(
    Object.entries(iconComponents).map(([key, value]) => [
      key.charAt(0).toLowerCase() + key.slice(1),
      value,
    ])
  ),
};
const isIconName = (name: string): name is IconName => name in iconsMap;
export const iconNames = Object.keys(iconsMap).filter(isIconName);

export const Icon = React.memo(
  React.forwardRef<SVGSVGElement, IconProps>(function Icon({ name, size, color, ...props }, ref) {
    const IconComponent = iconsMap[name];

    // TODO(ds): Extract color look up to a util
    const iconColor =
      color &&
      // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
      (theme.text[color as keyof GatherDesignSystemColors['text']] ??
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        theme.presence[color as keyof GatherDesignSystemColors['presence']] ??
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        theme.eventStatus[color as keyof GatherDesignSystemColors['eventStatus']] ??
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        theme.fg[color as keyof GatherDesignSystemColors['fg']]);

    if (!IconComponent) return null;

    return (
      <span className={iconRecipe({ size })}>
        <IconComponent className={iconStyle} color={iconColor} ref={ref} {...props} />
      </span>
    );
  })
);
