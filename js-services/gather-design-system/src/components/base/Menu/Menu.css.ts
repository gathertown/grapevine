import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';
import { textColorStyles } from '../Text/Text.css';

const MENU_MAX_WIDTH = 256;
const MENU_ITEM_MIN_HEIGHT = tokens.scale[28];

export const labelStyle = style({
  alignItems: 'center',
  color: theme.text.tertiaryOnDark,
  display: 'flex',
  fontSize: tokens.fontSize.xxs,
  height: tokens.scale[24],
  padding: `${tokens.scale[2]} ${tokens.scale[8]} 0`,
});

export const itemRecipe = recipe({
  base: {
    alignItems: 'center',
    borderRadius: tokens.borderRadius[6],
    cursor: 'pointer',
    display: 'flex',
    fontSize: tokens.fontSize.xs,
    fontWeight: tokens.fontWeight.normal,
    gap: tokens.scale[8],
    minHeight: MENU_ITEM_MIN_HEIGHT,
    padding: `0 ${tokens.scale[8]}`,
    position: 'relative',
    userSelect: 'none',

    selectors: {
      '&:hover': {
        backgroundColor: theme.bg.tertiaryHoverDark,
        outline: 'none',
      },
      "&[data-state='unchecked']": {
        color: theme.text.secondary,
      },
      "&[role='menuitemradio']": {
        // Padding + Icon + Gap
        paddingLeft: `calc(${tokens.scale[8]} + ${tokens.scale[16]} + ${tokens.scale[8]})`,
      },
    },
  },
  variants: {
    color: textColorStyles,
  },
  defaultVariants: {
    color: 'primaryOnDark',
  },
});

export const radioItemIndicatorStyle = style({
  left: tokens.scale[8],
  top: tokens.scale[8],
  position: 'absolute',
});

export const separatorStyle = style({
  backgroundColor: theme.border.quaternary,
  height: tokens.scale[1],
  margin: `${tokens.scale[6]} calc(-${tokens.scale[6]} + 1px)`,
});

export const contentStyle = style({
  backdropFilter: tokens.blur.md,
  borderRadius: tokens.borderRadius[12],
  boxShadow: `inset 0 0 0 1px ${theme.border.quaternary}, ${tokens.boxShadow.xl}`,
  width: MENU_MAX_WIDTH,
  // @ts-expect-error-next-line this is a valid property
  WebkitAppRegion: 'no-drag',
  backgroundColor: theme.bg.secondaryTransparentDark,
});

export const scrollableContainerStyle = style({
  height: '100%',
  maskImage: `linear-gradient(
    to bottom,
    transparent,
    black ${tokens.scale[4]},
    black calc(100% - ${tokens.scale[4]}),
    transparent 100%
  )`,
  maxHeight: 'calc(var(--radix-dropdown-menu-content-available-height) - 16px)',
  overflow: 'auto',
  padding: `${tokens.scale[6]}`,

  // TODO [APP-9194]: Create common scrollbar styles
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    '&::-webkit-scrollbar': {
      display: 'none',
    },
  },
});

export const keyboardShortcutStyle = style({
  marginLeft: 'auto',
});

export const arrowFillStyle = style({
  fill: theme.bg.secondary,
});
