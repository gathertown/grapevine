import { style, styleVariants } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const rootStyle = style({});

export const triggerStyle = style({});

export const contentRecipe = recipe({
  base: {
    padding: tokens.scale[8],
    borderRadius: tokens.borderRadius[12],
    boxShadow: tokens.boxShadow.xl,
    // @ts-expect-error-next-line this is a valid property
    WebkitAppRegion: 'no-drag',
  },
  variants: {
    noPadding: {
      true: {
        padding: 0,
      },
    },
    noBoxShadow: {
      true: {
        boxShadow: 'none',
      },
    },
  },
});

export const backgroundColorStyles = styleVariants(theme.bg, (backgroundColor) => ({
  backgroundColor,
}));

export const arrowFillStyles = styleVariants(theme.bg, (backgroundColor) => ({
  fill: backgroundColor,
}));
