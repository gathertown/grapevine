import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const customCheckboxRecipe = recipe({
  base: {
    borderRadius: tokens.scale[4],
    border: `1px solid ${theme.border.primary}`,
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
  },
  variants: {
    isChecked: {
      true: {
        backgroundColor: theme.bg.accentPrimary,
        borderColor: theme.bg.accentPrimary,
      },
    },
    isDisabled: {
      true: {
        backgroundColor: theme.bg.secondary,
        borderColor: theme.border.primaryDisabled,
      },
    },
    isFocused: {
      true: {
        boxShadow: `0px 0px 0px 3px ${theme.shadow.focusAccent}`,
      },
    },
    size: {
      sm: {
        width: tokens.scale[16],
        height: tokens.scale[16],
        marginTop: tokens.scale[2],
      },
      md: {
        width: tokens.scale[20],
        height: tokens.scale[20],
      },
    },
  },
  defaultVariants: {
    isChecked: false,
    isDisabled: false,
    isFocused: false,
    size: 'md',
  },
});

export const inputStyle = style({
  cursor: 'pointer',
  border: 'none',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  position: 'absolute',
  width: tokens.scale[18],
  height: tokens.scale[18],
  opacity: 0,
  top: 0,
  left: 0,
  margin: 0,
});
