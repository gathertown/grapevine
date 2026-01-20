import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const chatMentionRecipe = recipe({
  base: {
    appearance: 'none',
    display: 'inline',
    borderRadius: tokens.borderRadius[4],
    padding: tokens.scale[1],
  },
  variants: {
    highlighted: {
      false: {
        backgroundColor: theme.chat.mentionBg,
        color: theme.chat.mentionText,
      },
      true: {
        backgroundColor: theme.chat.highlightedMentionBg,
        color: theme.chat.highlightedMentionText,
      },
    },
    isClickable: {
      true: {
        cursor: 'pointer',
      },
    },
  },

  defaultVariants: {
    isClickable: false,
  },
});
