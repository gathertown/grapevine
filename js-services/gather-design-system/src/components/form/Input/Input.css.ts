import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const inputStyle = style({
  border: `1px solid ${theme.border.secondary}`,
  backgroundColor: theme.bg.primary,
  color: theme.text.primary,
  width: '100%',

  selectors: {
    '&::placeholder': {
      fontSize: tokens.fontSize.sm,
    },

    '&:focus-visible': {
      boxShadow: `0px 0px 0px 3px ${theme.shadow.focusPrimary}`,
      borderColor: theme.border.primary,
    },

    '&:hover': {
      borderColor: theme.border.primary,
    },

    '&:disabled': {
      backgroundColor: theme.bg.secondaryDisabled,
      cursor: 'default',
      pointerEvents: 'none',
    },
  },
});

export const inputRecipe = recipe({
  base: inputStyle,
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
        selectors: {
          '&:focus-visible': {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusDanger}`,
          },
        },
      },
    },
    size: {
      md: {
        borderRadius: tokens.borderRadius[8],
        height: tokens.scale[32],
        padding: `${tokens.scale[6]} ${tokens.scale[8]}`,
      },
      lg: {
        borderRadius: tokens.borderRadius[10],
        height: tokens.scale[36],
        padding: `${tokens.scale[8]} ${tokens.scale[10]}`,
        fontSize: tokens.fontSize.md,
      },
    },
    hasIcon: {
      true: {
        paddingLeft: tokens.scale[28],
      },
    },
    hasEndIcon: {
      true: {
        paddingRight: tokens.scale[28],
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export const iconRecipe = recipe({
  base: {
    position: 'absolute',
    top: '50%',
    transform: 'translateY(-50%)',
    pointerEvents: 'none',
  },
  variants: {
    isEnd: {
      true: { right: tokens.scale[8] },
      false: { left: tokens.scale[8] },
    },
  },
});

export type InputVariants = RecipeVariants<typeof inputRecipe>;
