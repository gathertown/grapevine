import { style } from '@vanilla-extract/css';

import { theme } from '@gathertown/gather-design-foundations';

export const dividerStyle = style({
  width: '1px',
  backgroundColor: theme.border.tertiary,
});
