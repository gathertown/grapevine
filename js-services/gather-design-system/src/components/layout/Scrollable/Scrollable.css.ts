import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

// Container styles
export const scrollContainerStyle = style({
  height: '100%',
  width: '100%',
  position: 'relative',

  // TODO [APP-9194]: Create common scrollbar styles
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    '&::-webkit-scrollbar': {
      display: 'none',
    },
  },
});

// Scrollbar track styles
export const scrollbarTrackRecipe = recipe({
  base: {
    position: 'absolute',
    // Brent decided to hide the tracks for now. We may eventually want to show them on hover (see
    // the way Linear does this), but this requires more nuanced interaction logic than Brent had
    // time for.
    backgroundColor: 'transparent',
    pointerEvents: 'none',
    borderRadius: 6,
    zIndex: 1000,
    transition: 'opacity 0.2s ease-in-out',
  },
  variants: {
    direction: {
      vertical: {
        top: 0,
        right: 0,
        width: 10,
      },
      horizontal: {
        bottom: 0,
        left: 0,
        height: 10,
      },
    },
    autoHide: {
      true: {
        opacity: 0,
        pointerEvents: 'none',
      },
      false: {
        opacity: 1,
        pointerEvents: 'auto',
      },
    },
    visible: {
      true: {
        opacity: 1,
        pointerEvents: 'auto',
      },
    },
  },
});

// Scrollbar thumb styles
export const scrollbarThumbStyle = style({
  position: 'absolute',
  backgroundColor: 'rgba(0, 0, 0, 0.4)',
  borderRadius: 4,
  transition: 'background-color 0.2s ease-in-out',
  pointerEvents: 'auto',

  selectors: {
    '&:hover': {
      backgroundColor: 'rgba(0, 0, 0, 0.5)',
    },
  },
});

export const verticalThumbStyle = style([
  scrollbarThumbStyle,
  {
    left: 2,
    width: 6,
  },
]);

export const horizontalThumbStyle = style([
  scrollbarThumbStyle,
  {
    top: 2,
    height: 6,
  },
]);
