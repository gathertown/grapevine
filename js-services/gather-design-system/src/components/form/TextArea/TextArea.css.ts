import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const textAreaStyle = style({
  border: `1px solid ${theme.border.tertiary}`,
  backgroundColor: theme.bg.primary,
  color: theme.text.primary,
  resize: 'none',
  width: '100%',

  selectors: {
    '&::placeholder': {
      fontWeight: tokens.fontWeight.medium,
      fontSize: tokens.fontSize.sm,
    },
    '&:focus': {
      borderColor: theme.border.secondary,
    },
  },
});

export const textAreaRecipe = recipe({
  base: textAreaStyle,
  variants: {
    disabled: {
      true: {
        backgroundColor: theme.bg.secondary,
        borderColor: theme.border.tertiary,
        color: theme.text.tertiary,
      },
    },
    hasError: {
      true: {
        borderColor: theme.border.dangerPrimary,
        color: theme.text.dangerPrimary,
      },
    },
    size: {
      sm: {
        borderRadius: tokens.borderRadius[8],
        minHeight: '56px',
        padding: `${tokens.scale[6]} ${tokens.scale[8]}`,
        fontSize: tokens.fontSize.sm,
      },
      md: {
        borderRadius: tokens.borderRadius[10],
        minHeight: '72px',
        padding: `${tokens.scale[8]} ${tokens.scale[10]}`,
        fontSize: tokens.fontSize.md,
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export type TextAreaVariants = RecipeVariants<typeof textAreaRecipe>;

export const errorStyle = style({
  color: theme.text.dangerPrimary,
  fontSize: tokens.fontSize.xs,
});
