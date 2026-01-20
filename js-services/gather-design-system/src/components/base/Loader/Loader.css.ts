import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { tokens } from '@gathertown/gather-design-foundations';
import { spinKeyframes } from '../../../styles/keyframes.css';

const loaderStyle = style({
  display: 'block',
  border: '2px solid currentColor',
  borderRightColor: 'transparent',
  borderRadius: tokens.borderRadius.full,
  animation: `${spinKeyframes} 0.8s linear infinite`,
});

export const loaderRecipe = recipe({
  base: loaderStyle,
  variants: {
    size: {
      sm: {
        height: tokens.scale[14],
        width: tokens.scale[14],
        borderWidth: tokens.scale[1],
      },
      md: {
        height: tokens.scale[16],
        width: tokens.scale[16],
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export type LoaderVariants = RecipeVariants<typeof loaderRecipe>;
