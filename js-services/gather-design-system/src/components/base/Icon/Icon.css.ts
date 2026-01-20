import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { tokens } from '@gathertown/gather-design-foundations';

export const iconRecipe = recipe({
  base: {
    display: 'flex',
    flexShrink: 0,
  },
  variants: {
    size: {
      inherit: { width: 'inherit' },
      xxxs: { width: tokens.scale[8] },
      xxs: { width: tokens.scale[12] },
      xs: { width: tokens.scale[14] },
      sm: { width: tokens.scale[16] },
      md: { width: tokens.scale[18] },
      lg: { width: tokens.scale[20] },
      xl: { width: tokens.scale[24] },
      ['100%']: { width: '100%' },
    },
  },
  defaultVariants: {
    size: 'lg',
  },
});

export const iconStyle = style({
  width: '100%',
  height: 'auto',
});

export type IconVariants = RecipeVariants<typeof iconRecipe>;
export type IconSize = NonNullable<IconVariants>['size'];
