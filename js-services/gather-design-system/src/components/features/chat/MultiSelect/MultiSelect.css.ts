import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const pillContainerRecipe = recipe({
  base: {
    borderRadius: 6,
    backgroundColor: theme.bg.tertiary,
    height: 28,
    padding: `${tokens.scale[4]} ${tokens.scale[6]}`,
    display: 'flex',
    alignItems: 'center',
    cursor: 'pointer',
    marginRight: 4,
    marginTop: 4,
    marginBottom: 4,
  },
  variants: {
    selected: {
      true: {
        backgroundColor: theme.bg.quaternary,
      },
    },
  },
});

export const dropdownRowContainerRecipe = recipe({
  base: {
    borderRadius: 10,
    padding: 8,
    cursor: 'pointer',
    backgroundColor: theme.bg.primary,
  },
  variants: {
    highlighted: {
      true: {
        backgroundColor: theme.bg.secondary,
      },
    },
  },
});
