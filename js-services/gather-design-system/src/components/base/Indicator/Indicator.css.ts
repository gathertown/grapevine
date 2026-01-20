import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const indicatorRecipe = recipe({
  base: {
    height: tokens.scale[12],
    width: tokens.scale[12],
    borderRadius: tokens.borderRadius.full,
    boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  variants: {
    kind: {
      primary: {
        background: theme.bg.dangerPrimary,
        color: theme.text.primaryOnDanger,
      },
      secondary: {
        background: theme.bg.tertiary,
        color: theme.text.primary,
      },
      tertiary: {
        background: theme.bg.accentPrimary,
        color: theme.text.primaryOnDark,
      },
      quaternary: {
        background: theme.text.primary,
        color: theme.text.primary,
      },
    },
    withCount: {
      true: {
        height: tokens.scale[16],
        minWidth: tokens.scale[16],
        padding: `0 ${tokens.scale[2]}`,
        width: 'fit-content',
      },
    },
  },
  defaultVariants: {
    kind: 'primary',
    withCount: false,
  },
});

export type IndicatorVariants = Exclude<RecipeVariants<typeof indicatorRecipe>, undefined>;
