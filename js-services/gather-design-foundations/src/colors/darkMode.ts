import { colorTokens, colorWithAlpha } from '../tokens/colors';
import { asColorToken } from '../tokens/typeHelpers';
import { dangerouslyStatic } from './_dangerouslyStatic';
import { GatherDesignSystemColors } from './colorContract.css';

// This config should be 1:1 with Figma color variables in DS Foundations

const text = {
  // Standard text colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.alphaWhite90,
  primaryDisabled: colorTokens.alphaWhite30,
  secondary: colorTokens.alphaWhite80,
  tertiary: colorTokens.alphaWhite60,
  quaternary: colorTokens.alphaWhite40,

  // Text colors for use on dark backgrounds—regardless of appearance setting
  primaryOnDark: colorTokens.alphaWhite90,
  secondaryOnDark: colorTokens.alphaWhite80,
  tertiaryOnDark: colorTokens.alphaWhite60,
  quaternaryOnDark: colorTokens.alphaWhite30,

  // Text colors for use on light backgrounds—regardless of appearance setting
  primaryOnLight: colorTokens.alphaBlack90,
  secondaryOnLight: colorTokens.alphaBlack80,
  tertiaryOnLight: colorTokens.alphaBlack60,
  quaternaryOnLight: colorTokens.alphaBlack40,

  // Status text colors
  successPrimary: colorTokens.green500,
  warningPrimary: colorTokens.orange400,
  dangerPrimary: colorTokens.red600,
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red600, 0.4)),
  primaryOnDanger: colorTokens.red50,
  disabledOnDanger: colorTokens.alphaWhite30,

  // Accent text colors
  accentPrimary: colorTokens.blue500,
  accentSecondary: colorTokens.blue400,
  accentTertiary: colorTokens.blue200,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.5)),
  disabledOnAccent: colorTokens.alphaWhite30,

  // Ambient text colors
  ambientPrimary: colorTokens.fuscia300,
  ambientSecondary: colorTokens.fuscia400,

  // Handraise text color
  handraisePrimary: colorTokens.yellow400,
} as const satisfies GatherDesignSystemColors['text'];

const bg = {
  // Standard background colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.gray900,
  secondary: colorTokens.gray800,
  secondaryTransparent: asColorToken(colorWithAlpha(colorTokens.gray800, 0.9)),
  secondaryHover: colorTokens.gray700,
  secondaryDisabled: asColorToken(colorWithAlpha(colorTokens.gray800, 0.4)),
  tertiary: colorTokens.gray700,
  tertiaryHover: colorTokens.alphaWhite7,
  quaternary: colorTokens.gray600,
  quintary: colorTokens.gray500,

  // Dark background colors—regardless of appearance setting
  primaryDark: colorTokens.gray900,
  primaryTransparentDark: asColorToken(colorWithAlpha(colorTokens.gray900, 0.9)),
  secondaryDark: colorTokens.gray800,
  secondaryTransparentDark: asColorToken(colorWithAlpha(colorTokens.gray800, 0.9)),
  tertiaryDark: colorTokens.gray700,
  tertiaryHoverDark: colorTokens.alphaWhite5,
  tertiaryTransparentDark: colorTokens.alphaBlack5,
  quaternaryDark: colorTokens.gray600,
  quintaryDark: colorTokens.gray50,

  // Light background colors—regardless of appearance setting
  primaryLight: colorTokens.white,
  primaryTransparentLight: colorTokens.alphaWhite90,
  secondaryLight: colorTokens.gray100,
  secondaryTransparentLight: asColorToken(colorWithAlpha(colorTokens.gray100, 0.9)),
  tertiaryLight: colorTokens.gray200,
  tertiaryHoverLight: colorTokens.alphaBlack3,
  tertiaryTransparentLight: colorTokens.alphaWhite7,
  quaternaryLight: colorTokens.gray300,
  quintaryLight: colorTokens.gray400,

  successPrimary: colorTokens.green600,
  successPrimaryHover: colorTokens.green500,
  successSecondary: colorTokens.green300,
  successTertiary: colorTokens.green100,

  warningPrimary: colorTokens.orange500,
  warningPrimaryHover: colorTokens.orange400,
  warningSecondary: colorTokens.orange300,
  warningTertiary: colorTokens.orange100,

  dangerPrimary: colorTokens.red600,
  dangerPrimaryHover: colorTokens.red500,
  dangerSecondary: colorTokens.red400,
  dangerTertiary: asColorToken(colorWithAlpha(colorTokens.red600, 0.07)),
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red500, 0.2)),

  accentPrimary: colorTokens.blue600,
  accentPrimaryHover: colorTokens.blue500,
  accentSecondary: colorTokens.blue400,
  accentSecondaryHover: asColorToken(colorWithAlpha(colorTokens.blue600, 0.1)),
  accentTertiary: asColorToken(colorWithAlpha(colorTokens.blue600, 0.2)),
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.3)),

  // Ambient background colors
  ambientPrimary: colorTokens.fuscia400,
  ambientSecondary: colorTokens.fuscia200,
  ambientTertiary: colorTokens.fuscia100,

  // Map background colors
  // TODO [VW-1003] Use more standard colors in map
  mapPrimary: colorTokens.purple300,
  mapCoworkingArea: colorTokens.fuscia500,

  // Background for main content panes
  mainContent: colorTokens.alphaWhite5,
} as const satisfies GatherDesignSystemColors['bg'];

const fg = {
  // Standard foreground colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.alphaWhite90,
  primaryDisabled: colorTokens.alphaWhite30,
  secondary: colorTokens.alphaWhite80,
  tertiary: colorTokens.alphaWhite60,
  quaternary: colorTokens.alphaWhite30,

  // Foreground colors for use on dark backgrounds—regardless of appearance setting
  primaryOnDark: colorTokens.alphaWhite90,
  secondaryOnDark: colorTokens.alphaWhite80,
  tertiaryOnDark: colorTokens.alphaWhite60,
  quaternaryOnDark: colorTokens.alphaWhite30,
  // [TODO] need to add disabledOnDark

  // Foreground colors for use on light backgrounds—regardless of appearance setting
  primaryOnLight: colorTokens.alphaBlack90,
  secondaryOnLight: colorTokens.alphaBlack80,
  tertiaryOnLight: colorTokens.alphaBlack60,
  quaternaryOnLight: colorTokens.alphaBlack40,

  // Status foreground colors
  successPrimary: colorTokens.green500,
  successSecondary: colorTokens.green300,

  warningPrimary: colorTokens.orange500,
  warningSecondary: colorTokens.orange300,

  dangerPrimary: colorTokens.red600,
  dangerSecondary: colorTokens.red400,
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red600, 0.4)),
  primaryOnDanger: colorTokens.red50,
  disabledOnDanger: colorTokens.alphaWhite30,

  // Accent foreground colors
  accentPrimary: colorTokens.blue500,
  accentSecondary: colorTokens.blue400,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.5)),
  disabledOnAccent: colorTokens.alphaWhite30,

  // Handraise foreground colors
  handraisePrimary: colorTokens.yellow400,
  handraiseSecondary: colorTokens.yellow200,
} as const satisfies GatherDesignSystemColors['fg'];

const border = {
  // Standard border colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.gray600,
  primaryDisabled: colorTokens.alphaBlack5,
  secondary: colorTokens.gray700,
  secondaryDisabled: asColorToken(colorWithAlpha(colorTokens.gray700, 0.3)),
  tertiary: colorTokens.alphaWhite10,
  quaternary: colorTokens.alphaWhite3,

  // Border colors for use on dark backgrounds—regardless of appearance setting
  primaryOnDark: colorTokens.alphaWhite60,
  secondaryOnDark: colorTokens.alphaWhite20,
  tertiaryOnDark: colorTokens.alphaWhite10,
  quaternaryOnDark: colorTokens.alphaWhite5,

  // Border colors for use on light backgrounds—regardless of appearance setting
  primaryOnLight: colorTokens.gray400,
  secondaryOnLight: colorTokens.gray300,
  tertiaryOnLight: colorTokens.alphaBlack10,
  quaternaryOnLight: colorTokens.alphaBlack5,

  // Accent border colors
  accentPrimary: colorTokens.blue300,
  accentSecondary: asColorToken(colorWithAlpha(colorTokens.blue600, 0.4)),
  accentTertiary: asColorToken(colorWithAlpha(colorTokens.blue600, 0.2)),
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.3)),

  // Status border colors
  successPrimary: colorTokens.green500,
  successSecondary: colorTokens.green200,
  successTertiary: colorTokens.green100,

  warningPrimary: colorTokens.orange500,
  warningSecondary: colorTokens.orange200,
  warningTertiary: colorTokens.orange100,

  dangerPrimary: colorTokens.red600,
  dangerSecondary: colorTokens.red200,
  dangerTertiary: colorTokens.red100,

  // [TODO] need to add handraise border colors

  // Ambient border colors
  ambientPrimary: colorTokens.fuscia400,
  ambientSecondary: colorTokens.fuscia400,
  ambientTertiary: colorTokens.fuscia400,
} as const satisfies GatherDesignSystemColors['border'];

const shadow = {
  inner: colorTokens.alphaWhite2,

  focusPrimary: colorTokens.alphaWhite5,
  focusAccent: asColorToken(colorWithAlpha(colorTokens.blue600, 0.3)),
  focusDanger: asColorToken(colorWithAlpha(colorTokens.red500, 0.3)),
} as const satisfies GatherDesignSystemColors['shadow'];

const av = {
  onPrimary: colorTokens.green500,
  onSecondary: asColorToken(colorWithAlpha(colorTokens.green500, 0.1)),
  onTertiary: asColorToken(colorWithAlpha(colorTokens.green500, 0.05)),
  offPrimary: colorTokens.red600,
  offSecondary: asColorToken(colorWithAlpha(colorTokens.red600, 0.15)),
  offTertiary: asColorToken(colorWithAlpha(colorTokens.red600, 0.1)),
} as const satisfies GatherDesignSystemColors['av'];

const presence = {
  online: colorTokens.green600,
  busy: colorTokens.orange500,
  away: colorTokens.orange500,
  offline: colorTokens.gray400,
} as const satisfies GatherDesignSystemColors['presence'];

const chat = {
  mentionText: text.accentSecondary,
  mentionBg: asColorToken(colorWithAlpha(text.accentPrimary, 0.16)),
  highlightedMentionText: colorTokens.teal300,
  highlightedMentionBg: asColorToken(colorWithAlpha(colorTokens.teal300, 0.16)),
  inlineCodeText: colorTokens.orange500,
  messageHighlightBg: asColorToken(colorWithAlpha(colorTokens.yellow600, 0.08)),
  selectedReactionBg: asColorToken(colorWithAlpha(colorTokens.teal300, 0.16)),
} as const satisfies GatherDesignSystemColors['chat'];

const eventStatus = {
  accepted: colorTokens.green600,
  declined: colorTokens.red500,
  needsAction: colorTokens.gray500,
  tentative: colorTokens.gray500,
} as const satisfies GatherDesignSystemColors['eventStatus'];

// Note: ui colors are an escape hatch; check with design before adding more colors here
const ui = {
  calendarAccent: colorTokens.red500,
  modalOverlay: colorTokens.alphaBlack30,
} as const satisfies GatherDesignSystemColors['ui'];

// TODO [VW-1003] Use more standard colors in map
// Note: map colors are an escape hatch; check with design before adding more colors here
const map = {
  mapPrimary: colorTokens.purple300,
  controls: colorTokens.alphaBlack30,
  actionSecondaryHovered: colorTokens.blue300,
  actionSecondaryPressed: colorTokens.blue500,
} as const satisfies GatherDesignSystemColors['map'];

// These map-inspired colors are used for placeholders in the UI
const placeholderPalette = {
  0: colorTokens.placeholder0,
  1: colorTokens.placeholder1,
  2: colorTokens.placeholder2,
  3: colorTokens.placeholder3,
  4: colorTokens.placeholder4,
  5: colorTokens.placeholder5,
  6: colorTokens.placeholder6,
  7: colorTokens.placeholder7,
} as const satisfies GatherDesignSystemColors['placeholderPalette'];

export const darkMode = {
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
} as const satisfies GatherDesignSystemColors;
