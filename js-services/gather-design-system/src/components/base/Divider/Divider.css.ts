import { style, styleVariants } from '@vanilla-extract/css';

import { theme } from '@gathertown/gather-design-foundations';

export const colorStyle = styleVariants(theme.border, (borderColor) => ({
  borderColor,
}));

export const horizontalStyle = style({
  borderStyle: 'solid',
  borderWidth: 0,
  borderTopWidth: '1px',
  flexGrow: 1,
});

export const verticalStyle = style({
  borderStyle: 'solid',
  borderWidth: 0,
  borderLeftWidth: '1px',
  flexGrow: 1,
});
