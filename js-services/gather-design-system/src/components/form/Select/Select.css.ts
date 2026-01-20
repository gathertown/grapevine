import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const selectTriggerRecipe = recipe({
  base: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: tokens.borderRadius[10],
    padding: `7px ${tokens.scale[8]} 7px ${tokens.scale[10]}`,
    backgroundColor: theme.bg.primary,
    border: `1px solid ${theme.border.secondary}`,
    fontSize: tokens.fontSize.sm,
    cursor: 'pointer',
    color: theme.text.secondary,
    gap: tokens.scale[4],
  },
  variants: {
    error: {
      true: {
        borderColor: theme.border.dangerPrimary,
      },
    },
    disabled: {
      true: {
        backgroundColor: theme.bg.secondary,
        borderColor: theme.border.tertiary,
        color: theme.text.tertiary,
      },
    },
  },
});

export const contentStyle = style({
  backgroundColor: theme.bg.primary,
  borderRadius: tokens.borderRadius[10],
  border: `1px solid ${theme.border.secondary}`,
  overflow: 'hidden',
  minWidth: 'var(--radix-select-trigger-width)',
  maxHeight: 'var(--radix-select-content-available-height)',
});

export const viewportStyle = style({
  padding: tokens.scale[4],
});

export const itemStyle = style({
  fontSize: tokens.fontSize.sm,
  padding: `${tokens.scale[8]} ${tokens.scale[12]}`,
  borderRadius: tokens.borderRadius[8],
  display: 'flex',
  alignItems: 'center',
  cursor: 'pointer',
  justifyContent: 'space-between',
  gap: tokens.scale[8],

  selectors: {
    '&[data-highlighted]': {
      backgroundColor: theme.bg.secondary,
      outline: 'none',
    },
  },
});

export const errorStyle = style({
  fontSize: tokens.fontSize.sm,
  color: theme.text.dangerPrimary,
  marginTop: tokens.scale[4],
});
