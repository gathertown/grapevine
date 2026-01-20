import { style } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const tooltipStyle = style({
  padding: `${tokens.scale[6]} ${tokens.scale[8]}`,
  borderRadius: tokens.borderRadius[8],
  background: theme.bg.primaryDark,
  fill: theme.bg.primaryDark,
  color: theme.text.primaryOnDark,
  fontSize: tokens.fontSize.xs,
  fontWeight: tokens.fontWeight.medium,
});

export const arrowFillStyle = style({
  fill: theme.bg.primaryDark,
});
