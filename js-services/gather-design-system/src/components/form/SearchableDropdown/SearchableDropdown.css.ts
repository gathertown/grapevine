import { style } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const container = style({
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: theme.bg.secondary,
  border: `1px solid ${theme.border.secondary}`,
  borderRadius: tokens.borderRadius[12],
  boxShadow: tokens.boxShadow.md,
  overflow: 'hidden',
});

export const inputContainer = style({
  display: 'flex',
  alignItems: 'center',
  position: 'relative',
  padding: tokens.scale[8],
});

export const input = style({
  appearance: 'none',
  width: '100%',
  height: tokens.scale[36],
  padding: `0 ${tokens.scale[12]}`,
  paddingRight: tokens.scale[56],
  border: `1px solid ${theme.border.secondary}`,
  borderRadius: tokens.borderRadius[10],
  fontSize: tokens.fontSize.xs,
  fontFamily: 'inherit',
  backgroundColor: 'inherit',
  color: theme.text.primary,
  outline: 'none',

  selectors: {
    ['&::placeholder']: {
      color: theme.text.tertiary,
    },

    ['&:hover:not([disabled])']: {
      borderColor: theme.border.secondary,
    },

    ['&:focus']: {
      borderColor: theme.border.tertiary,
      color: theme.text.secondary,
    },
  },
});

export const inputError = style([
  input,
  {
    borderColor: theme.text.dangerPrimary,

    selectors: {
      ['&:focus']: {
        borderColor: theme.text.dangerPrimary,
      },
    },
  },
]);

export const clearButton = style({
  position: 'absolute',
  right: `calc(${tokens.scale[8]} + ${tokens.scale[4]})`,
  top: '50%',
  transform: 'translateY(-50%)',
  color: theme.text.tertiary,

  selectors: {
    ['&:hover']: {
      color: theme.text.secondary,
    },
  },
});

export const errorMessage = style({
  padding: `${tokens.scale[4]} ${tokens.scale[8]}`,
  fontSize: tokens.fontSize.xs,
  color: theme.text.dangerPrimary,
  backgroundColor: theme.bg.secondary,
  borderBottom: `1px solid ${theme.border.secondary}`,
});

export const scrollContainer = style({
  flex: 1,
  overflowY: 'auto',
  maxHeight: 'inherit',

  // Hide scrollbars - same pattern as DeskManagerPopover
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    ['&::-webkit-scrollbar']: {
      display: 'none',
    },
  },
});

export const sectionHeader = style({
  display: 'flex',
  gap: tokens.scale[8],
  padding: tokens.scale[8],
  fontSize: tokens.fontSize.xs,
  fontWeight: tokens.fontWeight.semibold,
  color: theme.text.primary,
  backgroundColor: 'transparent',
});

export const dropdownItem = style({
  cursor: 'pointer',

  selectors: {
    ['&:hover']: {
      backgroundColor: theme.bg.tertiaryHover,
    },
  },
});

export const dropdownItemKeyboardMode = style({
  cursor: 'pointer',

  selectors: {
    // Disable hover when in keyboard mode
    ['&:hover']: {
      backgroundColor: 'transparent',
    },
  },
});

export const dropdownItemHighlighted = style({
  cursor: 'pointer',
  backgroundColor: theme.bg.tertiaryHover,
});
