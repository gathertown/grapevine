import { style } from '@vanilla-extract/css';

export const pixelatedImageStyle = style({
  imageRendering: 'pixelated',
});

export const disabledAnimations = style({
  animation: 'none !important',
  transition: 'none !important',
});
