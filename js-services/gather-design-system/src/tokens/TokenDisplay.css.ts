import { style } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const tokenGrid = style({
  display: 'flex',
  flexDirection: 'column',
  gap: tokens.scale[16],
  margin: `${tokens.scale[32]} 0`,
  width: '100%',
});

const gridBase = {
  display: 'grid',
  gridTemplateColumns: 'minmax(280px, auto) minmax(120px, auto) 1fr',
  gap: tokens.scale[24],
};

export const tokenHeader = style({
  ...gridBase,
  borderBottom: `1px solid ${theme.border.secondary}`,
  paddingBottom: tokens.scale[8],
  fontSize: tokens.fontSize.sm,
});

export const tokenRow = style({
  ...gridBase,
  alignItems: 'center',
});

export const tokenValue = style({
  color: theme.text.secondary,
  fontFamily: 'monospace',
  whiteSpace: 'nowrap',
});

export const tokenCode = style({
  fontFamily: 'monospace',
  fontSize: tokens.fontSize.sm,
  padding: `${tokens.scale[4]} ${tokens.scale[8]}`,
  borderRadius: tokens.borderRadius[4],
  display: 'inline-block',
  whiteSpace: 'nowrap',
});
