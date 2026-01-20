import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const ITEM_HEIGHT = 30;

export const dropdownContainerStyle = style({
  display: 'flex',
  flexDirection: 'column',
  position: 'relative',
  borderRadius: tokens.borderRadius[12],
  backgroundColor: theme.bg.secondaryTransparentDark,
  fontSize: tokens.fontSize.md,
  minWidth: 120,
  maxHeight: 192,
  boxShadow: `inset 0 0 0 1px ${theme.border.quaternary}, ${tokens.boxShadow.xl}`,
  userSelect: 'none',
});

export const dropdownItemRecipe = recipe({
  base: {
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    height: ITEM_HEIGHT,
    minWidth: '100%',
    padding: `${tokens.scale[4]} ${tokens.scale[8]}`,
    border: 'none',
    cursor: 'pointer',
    borderRadius: tokens.borderRadius[6],
    color: theme.text.primaryOnDark,
    backgroundColor: 'transparent',
    overflow: 'hidden',
  },
  variants: {
    isSelected: {
      true: {
        backgroundColor: theme.dangerouslyStatic.alphaWhite10,
      },
      false: {},
    },
  },
});
