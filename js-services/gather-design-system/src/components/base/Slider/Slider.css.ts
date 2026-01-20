import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const sliderRootStyle = recipe({
  base: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    userSelect: 'none',
    touchAction: 'none',
    width: '100%',
  },
  variants: {
    orientation: {
      horizontal: {
        height: tokens.scale[20],
      },
      vertical: {
        flexDirection: 'column',
        width: tokens.scale[20],
        height: '100%',
      },
    },
  },
  defaultVariants: {
    orientation: 'horizontal',
  },
});

export const sliderTrackStyle = recipe({
  base: {
    backgroundColor: theme.bg.quaternary,
    position: 'relative',
    flexGrow: 1,
    borderRadius: tokens.borderRadius.full,
  },
  variants: {
    orientation: {
      horizontal: {
        height: tokens.scale[4],
      },
      vertical: {
        width: tokens.scale[4],
      },
    },
  },
});

export const sliderRangeStyle = recipe({
  base: {
    position: 'absolute',
    backgroundColor: theme.bg.accentPrimary,
    borderRadius: tokens.borderRadius.full,
  },
  variants: {
    orientation: {
      horizontal: {
        height: '100%',
      },
      vertical: {
        width: '100%',
      },
    },
  },
});

export const sliderThumbStyle = recipe({
  base: {
    display: 'block',
    width: tokens.scale[16],
    height: tokens.scale[16],
    backgroundColor: theme.bg.accentPrimary,
    boxShadow: tokens.boxShadow.sm,
    borderRadius: tokens.borderRadius.full,
    cursor: 'pointer',
    transition: 'transform 200ms',
    ':hover': {
      transform: 'scale(1.1)',
    },
    ':focus': {
      outline: 'none',
      boxShadow: `0 0 0 2px ${theme.border.quaternary}`,
    },
  },
  variants: {
    disabled: {
      true: {
        cursor: 'not-allowed',
        opacity: 0.5,
        ':hover': {
          transform: 'none',
        },
      },
    },
  },
});
