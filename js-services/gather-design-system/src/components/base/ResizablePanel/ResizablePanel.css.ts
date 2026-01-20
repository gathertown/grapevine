import { recipe } from '@vanilla-extract/recipes';

import { theme } from '@gathertown/gather-design-foundations';

const DRAG_HANDLE_WIDTH = 10;
const BORDER_WIDTH = 1;

export const panelResizeHandleRecipe = recipe({
  base: {
    position: 'relative',
    width: DRAG_HANDLE_WIDTH,
    // This should take up space to be draggable, yet the panels beside it should not be pushed by the
    // handle.
    margin: -DRAG_HANDLE_WIDTH / 2,
    zIndex: 10,

    '::before': {
      content: '""',
      position: 'absolute',
      top: 0,
      left: '50%',
      width: BORDER_WIDTH,
      height: '100%',
    },
  },
  variants: {
    highlighted: {
      true: {
        ':before': {
          backgroundColor: theme.border.accentSecondary,
          width: 2,
          transform: 'translateX(-50%)',
        },
      },
    },
  },
});
