import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const labelStyle = style({
  fontWeight: tokens.fontWeight.medium,
  lineHeight: 'normal',
});

export const labelRecipe = recipe({
  base: labelStyle,
  variants: {
    size: {
      sm: {
        fontSize: tokens.fontSize.xs,
      },
      md: {
        fontSize: tokens.fontSize.sm,
      },
    },
    hasCursor: {
      true: {
        cursor: 'pointer',
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export const requiredStyle = style({
  color: theme.text.accentPrimary,
});

export type LabelVariants = RecipeVariants<typeof labelRecipe>;
