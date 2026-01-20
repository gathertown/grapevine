import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const customRadioRecipe = recipe({
  base: {
    borderRadius: tokens.borderRadius.full,
    border: `1px solid ${theme.border.primary}`,
    position: 'relative',
  },
  variants: {
    isChecked: {
      true: {
        background: theme.bg.accentPrimary,
        borderColor: theme.border.accentPrimary,

        selectors: {
          '&:after': {
            background: theme.bg.primaryLight,
            borderRadius: tokens.borderRadius.full,
            content: '""',
            left: '50%',
            position: 'absolute',
            top: '50%',
            transform: 'translate(-50%, -50%)',
          },
        },
      },
    },
    isDisabled: {
      true: {
        background: theme.bg.secondary,
        borderColor: theme.border.primaryDisabled,

        selectors: {
          '&:after': {
            background: theme.bg.quaternary,
          },
        },
      },
    },
    isFocused: {
      true: {
        boxShadow: `0px 0px 0px 3px ${theme.shadow.focusAccent}`,
      },
    },
    size: {
      xs: {
        minWidth: tokens.scale[12],
        height: tokens.scale[12],
        marginTop: tokens.scale[2],

        selectors: {
          '&:after': {
            width: tokens.scale[4],
            height: tokens.scale[4],
          },
        },
      },
      sm: {
        minWidth: tokens.scale[16],
        height: tokens.scale[16],
        marginTop: tokens.scale[2],

        selectors: {
          '&:after': {
            width: tokens.scale[6],
            height: tokens.scale[6],
          },
        },
      },
      md: {
        minWidth: tokens.scale[20],
        height: tokens.scale[20],

        selectors: {
          '&:after': {
            width: tokens.scale[8],
            height: tokens.scale[8],
          },
        },
      },
    },
  },
  defaultVariants: {
    isChecked: false,
    size: 'md',
  },
});

export const inputStyle = style({
  position: 'absolute',
  opacity: 0,
  inset: 0,
  margin: 0,
  width: tokens.scale[20],
  height: tokens.scale[20],
});
