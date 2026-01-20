import { createVar, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const hotkeySize = createVar();

export const hotkeyStyle = style({
  alignItems: 'center',
  border: `0.5px solid ${theme.border.tertiary}`,
  color: theme.text.tertiary,
  display: 'inline-flex',
  fontWeight: tokens.fontWeight.medium,
  lineHeight: hotkeySize,
  height: hotkeySize,
  justifyContent: 'center',
  minWidth: hotkeySize,
  textTransform: 'capitalize',
});

export const hotkeyRecipe = recipe({
  base: hotkeyStyle,
  variants: {
    size: {
      sm: {
        borderRadius: tokens.borderRadius[4],
        fontSize: tokens.fontSize.xxs,
        padding: tokens.scale[2],
        vars: {
          [hotkeySize]: tokens.scale[16],
        },
      },
      md: {
        borderRadius: tokens.borderRadius[6],
        fontSize: tokens.fontSize.xs,
        padding: tokens.scale[4],
        vars: {
          [hotkeySize]: tokens.scale[20],
        },
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export const specialKeyStyle = style({
  width: hotkeySize,
});
