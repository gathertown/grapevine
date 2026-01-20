import { style } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const segmentedControlHeight = tokens.scale[28];
const segmentedControlPadding = tokens.scale[2];
const highlightBarBorderRadius = tokens.scale[8];

export const segmentedControlWrapper = style({
  position: 'relative',
  alignItems: 'center',
  backgroundColor: theme.bg.secondary,
  borderRadius: `calc(${highlightBarBorderRadius} + ${segmentedControlPadding})`,
  color: theme.text.secondary,
  display: 'flex',
  height: segmentedControlHeight,
  padding: `0px ${segmentedControlPadding}`,
});

export const highlightBar = style({
  position: 'absolute',
  top: tokens.scale[2],
  left: 0,
  height: tokens.scale[24],
  backgroundColor: theme.bg.primary,
  boxShadow: tokens.boxShadow.sm,
  borderRadius: highlightBarBorderRadius,
  transition: 'transform 200ms ease-out',
  willChange: 'transform',
});

export const segmentStyle = style({
  appearance: 'none',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  flexGrow: 1,
  height: '100%',
  textAlign: 'center',
  alignItems: 'center',
  transition: 'color 150ms ease-in-out',
  position: 'relative',
  zIndex: 1,
});
