import { createVar, style } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const tabListWidth = createVar();

export const tabsRootStyle = style({
  vars: {
    [tabListWidth]: '216px',
  },
  display: 'flex',
  height: '100%',
});

export const tabsListStyle = style({
  backgroundColor: theme.bg.secondary,
  borderRight: `1px solid ${theme.border.quaternary}`,
  flexShrink: '0',
  maxHeight: '100%',
  overflow: 'scroll',
  padding: `${tokens.scale[20]} ${tokens.scale[12]}`,
  width: tabListWidth,

  // TODO [APP-9194]: Create common scrollbar styles
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    '&::-webkit-scrollbar': {
      display: 'none',
    },
  },
});

export const tabsTriggerStyle = style({
  alignItems: 'center',
  background: 'none',
  border: 'none',
  borderRadius: tokens.borderRadius[8],
  color: theme.text.secondary,
  cursor: 'pointer',
  display: 'flex',
  fontSize: tokens.fontSize.sm,
  gap: tokens.scale[8],
  padding: `${tokens.scale[6]} ${tokens.scale[12]} ${tokens.scale[6]} ${tokens.scale[8]}`,
  whiteSpace: 'nowrap',
  width: '100%',

  selectors: {
    '&:hover': {
      transition: 'background-color 100ms ease-in-out',
      backgroundColor: theme.bg.tertiaryHover,
    },

    "&[data-state='active']": {
      backgroundColor: theme.bg.accentPrimary,
      // TODO: Consider creating gradient tokens
      backgroundImage: `linear-gradient(90deg, ${theme.bg.accentPrimary}, color-mix(in sRGB, ${theme.bg.accentPrimary}, white 10%))`,
      // TODO: Create token for maintaining contrast on bg.accentPrimary
      color: theme.text.primaryOnDark,
    },
  },
});

export const tabsContentStyle = style({
  border: 'none !important',
  display: 'flex',
  flexDirection: 'column',
  flexGrow: '1',
  maxWidth: `calc(100% - ${tabListWidth} + ${tokens.scale[8]})`,
  outline: 'none !important',
  overflowY: 'scroll',

  // TODO [APP-9194]: Create common scrollbar styles
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    '&::-webkit-scrollbar': {
      display: 'none',
    },

    "&[data-state='inactive']": {
      display: 'none',
    },
  },
});

export const tabsIconImageStyle = style({
  width: '100%',
  height: '100%',
  transformOrigin: 'center',
});

export const tabsIconImageContainerStyles = style({
  width: tokens.scale[32],
  height: tokens.scale[32],
});
