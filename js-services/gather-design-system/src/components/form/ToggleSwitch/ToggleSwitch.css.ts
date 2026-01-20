import { createVar, style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const toggleWidth = createVar();
const toggleHeight = createVar();
const toggleSpacing = tokens.scale[6];

export const toggleStyle = style({
  display: 'inline-flex',
  gap: tokens.scale[10],
});

export const toggleInputStyle = style({
  opacity: 0,
  appearance: 'none',
  position: 'absolute',
});

export const toggleFillRecipe = recipe({
  base: {
    backgroundColor: theme.bg.quaternary,
    borderRadius: tokens.borderRadius.full,
    flexShrink: 0,
    height: toggleHeight,
    position: 'relative',
    transition: 'background-color 100ms ease-in-out',
    width: toggleWidth,

    selectors: {
      '&::after': {
        aspectRatio: '1 / 1',
        background: theme.dangerouslyStatic.white,
        borderRadius: tokens.borderRadius.full,
        boxShadow: tokens.boxShadow.xs,
        content: '""',
        height: `calc(${toggleHeight} - ${toggleSpacing})`,
        left: `calc(${toggleSpacing} / 2)`,
        position: 'absolute',
        top: `calc(${toggleSpacing} / 2)`,
        transition: 'transform 100ms ease-in-out',
      },

      [`${toggleInputStyle}:focus-visible + &`]: {
        boxShadow: `0px 0px 0px 3px ${theme.shadow.focusAccent}`,
      },

      [`${toggleInputStyle}:checked + &`]: {
        backgroundColor: theme.bg.accentPrimary,
      },

      [`${toggleInputStyle}:checked + &:hover`]: {
        backgroundColor: theme.bg.accentPrimaryHover,
      },

      [`${toggleInputStyle}:checked + &::after`]: {
        transform: `translateX(calc(${toggleWidth} - ${toggleHeight}))`,
      },

      [`${toggleInputStyle}:disabled + &`]: {
        backgroundColor: theme.bg.secondary,
        boxShadow: `inset 0 0 0 1px ${theme.border.tertiary}`,
        pointerEvents: 'none',
      },

      [`${toggleInputStyle}:checked:disabled + &`]: {
        backgroundColor: theme.bg.accentSecondary,
      },
    },
  },
  variants: {
    size: {
      sm: {
        vars: {
          [toggleWidth]: tokens.scale[24],
          [toggleHeight]: tokens.scale[20],
        },
      },
      md: {
        vars: {
          [toggleWidth]: tokens.scale[32],
          [toggleHeight]: tokens.scale[20],
        },
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export type ToggleSwitchVariants = RecipeVariants<typeof toggleFillRecipe>;
