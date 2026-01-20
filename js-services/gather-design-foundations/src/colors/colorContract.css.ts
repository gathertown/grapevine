import { createThemeContract } from '@vanilla-extract/css';

import { asColorToken } from '../tokens/typeHelpers';

const colorToken = asColorToken('colorToken');

// This theme contract should be 1:1 with Figma color variables in DS Foundations

const text = {
  // Standard text colors; will resolve to light or dark dependent on theme
  primary: colorToken,
  primaryDisabled: colorToken,
  secondary: colorToken,
  tertiary: colorToken,
  quaternary: colorToken,

  // Text colors for use on dark backgrounds—regardless of theme
  primaryOnDark: colorToken,
  secondaryOnDark: colorToken,
  tertiaryOnDark: colorToken,
  quaternaryOnDark: colorToken,

  // Text colors for use on light backgrounds—regardless of theme
  primaryOnLight: colorToken,
  secondaryOnLight: colorToken,
  tertiaryOnLight: colorToken,
  quaternaryOnLight: colorToken,

  // Status text colors
  successPrimary: colorToken,
  warningPrimary: colorToken,
  dangerPrimary: colorToken,
  dangerDisabled: colorToken,
  primaryOnDanger: colorToken,
  disabledOnDanger: colorToken,

  // Accent text colors
  accentPrimary: colorToken,
  accentSecondary: colorToken,
  accentTertiary: colorToken,
  accentDisabled: colorToken,
  disabledOnAccent: colorToken,

  // Ambient text colors
  ambientPrimary: colorToken,
  ambientSecondary: colorToken,

  // Handraise text color
  handraisePrimary: colorToken,
} as const;

const bg = {
  // Standard background colors; will resolve to light or dark dependent on theme
  primary: colorToken,
  secondary: colorToken,
  secondaryTransparent: colorToken,
  secondaryHover: colorToken,
  secondaryDisabled: colorToken,
  tertiary: colorToken,
  tertiaryHover: colorToken,
  quaternary: colorToken,
  quintary: colorToken,

  // Dark background colors—regardless of theme
  primaryDark: colorToken,
  primaryTransparentDark: colorToken,
  secondaryDark: colorToken,
  secondaryTransparentDark: colorToken,
  tertiaryDark: colorToken,
  tertiaryHoverDark: colorToken,
  tertiaryTransparentDark: colorToken,
  quaternaryDark: colorToken,
  quintaryDark: colorToken,

  // Light background colors—regardless of theme
  primaryLight: colorToken,
  primaryTransparentLight: colorToken,
  secondaryLight: colorToken,
  secondaryTransparentLight: colorToken,
  tertiaryLight: colorToken,
  tertiaryHoverLight: colorToken,
  tertiaryTransparentLight: colorToken,
  quaternaryLight: colorToken,
  quintaryLight: colorToken,

  // Status background colors
  successPrimary: colorToken,
  successPrimaryHover: colorToken,
  successSecondary: colorToken,
  successTertiary: colorToken,

  warningPrimary: colorToken,
  warningPrimaryHover: colorToken,
  warningSecondary: colorToken,
  warningTertiary: colorToken,

  dangerPrimary: colorToken,
  dangerPrimaryHover: colorToken,
  dangerSecondary: colorToken,
  dangerTertiary: colorToken,
  dangerDisabled: colorToken,

  // Accent background colors
  accentPrimary: colorToken,
  accentPrimaryHover: colorToken,
  accentSecondary: colorToken,
  accentSecondaryHover: colorToken,
  accentTertiary: colorToken,
  accentDisabled: colorToken,

  // Ambient background colors
  ambientPrimary: colorToken,
  ambientSecondary: colorToken,
  ambientTertiary: colorToken,

  // Map background colors
  // TODO [VW-1003] Use more standard colors in map
  mapPrimary: colorToken,
  mapCoworkingArea: colorToken,

  // Background for main content panes
  mainContent: colorToken,
} as const;

const fg = {
  // Standard foreground colors; will resolve to light or dark dependent on theme
  primary: colorToken,
  primaryDisabled: colorToken,
  secondary: colorToken,
  tertiary: colorToken,
  quaternary: colorToken,

  // Foreground colors for use on dark backgrounds—regardless of theme
  primaryOnDark: colorToken,
  secondaryOnDark: colorToken,
  tertiaryOnDark: colorToken,
  quaternaryOnDark: colorToken,

  // Foreground colors for use on light backgrounds—regardless of theme
  primaryOnLight: colorToken,
  secondaryOnLight: colorToken,
  tertiaryOnLight: colorToken,
  quaternaryOnLight: colorToken,

  // Status foreground colors
  successPrimary: colorToken,
  successSecondary: colorToken,

  warningPrimary: colorToken,
  warningSecondary: colorToken,

  dangerPrimary: colorToken,
  dangerSecondary: colorToken,
  dangerDisabled: colorToken,
  primaryOnDanger: colorToken,
  disabledOnDanger: colorToken,

  // Accent foreground colors
  accentPrimary: colorToken,
  accentSecondary: colorToken,
  accentDisabled: colorToken,
  disabledOnAccent: colorToken,

  // Handraise foreground colors
  handraisePrimary: colorToken,
  handraiseSecondary: colorToken,
} as const;

const border = {
  // Standard border colors; will resolve to light or dark dependent on theme
  primary: colorToken,
  primaryDisabled: colorToken,
  secondary: colorToken,
  secondaryDisabled: colorToken,
  tertiary: colorToken,
  quaternary: colorToken,

  // Border colors for use on dark backgrounds—regardless of theme
  primaryOnDark: colorToken,
  secondaryOnDark: colorToken,
  tertiaryOnDark: colorToken,
  quaternaryOnDark: colorToken,

  // Border colors for use on light backgrounds—regardless of theme
  primaryOnLight: colorToken,
  secondaryOnLight: colorToken,
  tertiaryOnLight: colorToken,
  quaternaryOnLight: colorToken,

  // Accent border colors
  accentPrimary: colorToken,
  accentSecondary: colorToken,
  accentTertiary: colorToken,
  accentDisabled: colorToken,

  // Status border colors
  successPrimary: colorToken,
  successSecondary: colorToken,
  successTertiary: colorToken,

  warningPrimary: colorToken,
  warningSecondary: colorToken,
  warningTertiary: colorToken,

  dangerPrimary: colorToken,
  dangerSecondary: colorToken,
  dangerTertiary: colorToken,

  // Ambient border colors
  ambientPrimary: colorToken,
  ambientSecondary: colorToken,
  ambientTertiary: colorToken,
} as const;

const shadow = {
  inner: colorToken,

  focusPrimary: colorToken,
  focusAccent: colorToken,
  focusDanger: colorToken,
} as const;

const av = {
  onPrimary: colorToken,
  onSecondary: colorToken,
  onTertiary: colorToken,
  offPrimary: colorToken,
  offSecondary: colorToken,
  offTertiary: colorToken,
} as const;

const presence = {
  online: colorToken,
  busy: colorToken,
  away: colorToken,
  offline: colorToken,
} as const;

const chat = {
  mentionText: colorToken,
  mentionBg: colorToken,
  highlightedMentionText: colorToken,
  highlightedMentionBg: colorToken,
  inlineCodeText: colorToken,
  messageHighlightBg: colorToken,
  selectedReactionBg: colorToken,
} as const;

const eventStatus = {
  accepted: colorToken,
  declined: colorToken,
  needsAction: colorToken,
  tentative: colorToken,
} as const;

// Note: ui colors are an escape hatch; check with design before adding more colors here
const ui = {
  // Although this closely matches dangerPrimary, this escape hatch exists so we don't
  // use danger color tokens for UI elements that don't represent danger
  calendarAccent: colorToken,
  modalOverlay: colorToken,
} as const;

// TODO [VW-1003] Use more standard colors in map
// Note: map colors are an escape hatch; check with design before adding more colors here
const map = {
  mapPrimary: colorToken,
  controls: colorToken,
  actionSecondaryHovered: colorToken,
  actionSecondaryPressed: colorToken,
} as const;

const placeholderPalette = {
  0: colorToken,
  1: colorToken,
  2: colorToken,
  3: colorToken,
  4: colorToken,
  5: colorToken,
  6: colorToken,
  7: colorToken,
} as const;

// Static colors are the same between themes
const dangerouslyStatic = {
  // White with transparency
  alphaWhite2: colorToken,
  alphaWhite3: colorToken,
  alphaWhite5: colorToken,
  alphaWhite7: colorToken,
  alphaWhite10: colorToken,
  alphaWhite20: colorToken,
  alphaWhite30: colorToken,
  alphaWhite40: colorToken,
  alphaWhite50: colorToken,
  alphaWhite60: colorToken,
  alphaWhite70: colorToken,
  alphaWhite80: colorToken,
  alphaWhite90: colorToken,
  white: colorToken,

  // Black with transparency
  alphaBlack2: colorToken,
  alphaBlack3: colorToken,
  alphaBlack5: colorToken,
  alphaBlack7: colorToken,
  alphaBlack10: colorToken,
  alphaBlack20: colorToken,
  alphaBlack30: colorToken,
  alphaBlack40: colorToken,
  alphaBlack50: colorToken,
  alphaBlack60: colorToken,
  alphaBlack70: colorToken,
  alphaBlack80: colorToken,
  alphaBlack90: colorToken,
  black: colorToken,
} as const;

export const colorContract = {
  text,
  bg,
  fg,
  border,
  shadow,
  av,
  presence,
  chat,
  eventStatus,
  ui,
  map,
  placeholderPalette,
  dangerouslyStatic,
} as const;

export const colors = createThemeContract(colorContract);

export type GatherDesignSystemColors = typeof colorContract;
