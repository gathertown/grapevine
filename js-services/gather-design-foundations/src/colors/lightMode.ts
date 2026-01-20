import { colorTokens, colorWithAlpha } from '../tokens/colors';
import { asColorToken } from '../tokens/typeHelpers';
import { dangerouslyStatic } from './_dangerouslyStatic';
import { GatherDesignSystemColors } from './colorContract.css';

// This config should be 1:1 with Figma color variables in DS Foundations

const text = {
  // Standard text colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.alphaBlack90,
  primaryDisabled: colorTokens.alphaBlack30,
  secondary: colorTokens.alphaBlack80,
  tertiary: colorTokens.alphaBlack60,
  quaternary: colorTokens.alphaBlack40,

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
  successPrimary: colorTokens.green600,
  warningPrimary: colorTokens.orange500,
  dangerPrimary: colorTokens.red600,
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red600, 0.3)),
  primaryOnDanger: colorTokens.red50,
  disabledOnDanger: colorTokens.alphaWhite80,

  // Accent text colors
  accentPrimary: colorTokens.blue600,
  accentSecondary: colorTokens.blue400,
  accentTertiary: colorTokens.blue200,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.4)),
  disabledOnAccent: colorTokens.alphaWhite50,

  // Ambient text colors
  ambientPrimary: colorTokens.fuscia400,
  ambientSecondary: colorTokens.fuscia300,

  // Handraise text color
  handraisePrimary: colorTokens.yellow400,
} as const satisfies GatherDesignSystemColors['text'];

const bg = {
  // Standard background colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.white,
  secondary: colorTokens.gray100,
  secondaryHover: colorTokens.gray50,
  secondaryTransparent: asColorToken(colorWithAlpha(colorTokens.gray100, 0.9)),
  secondaryDisabled: asColorToken(colorWithAlpha(colorTokens.gray100, 0.6)),
  tertiary: colorTokens.gray200,
  tertiaryHover: colorTokens.alphaBlack5,
  quaternary: colorTokens.gray300,
  quintary: colorTokens.gray400,

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
  successTertiary: colorTokens.green50,

  warningPrimary: colorTokens.orange500,
  warningPrimaryHover: colorTokens.orange400,
  warningSecondary: colorTokens.orange300,
  warningTertiary: colorTokens.orange50,

  dangerPrimary: colorTokens.red600,
  dangerPrimaryHover: colorTokens.red500,
  dangerSecondary: colorTokens.red400,
  dangerTertiary: colorTokens.red50,
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red500, 0.3)),

  accentPrimary: colorTokens.blue600,
  accentPrimaryHover: colorTokens.blue500,
  accentSecondary: colorTokens.blue400,
  accentSecondaryHover: asColorToken(colorWithAlpha(colorTokens.blue600, 0.03)),
  accentTertiary: colorTokens.blue50,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.4)),

  // Ambient background colors
  ambientPrimary: colorTokens.fuscia400,
  ambientSecondary: colorTokens.fuscia200,
  ambientTertiary: colorTokens.fuscia100,

  // Map background colors
  // TODO [VW-1003] Use more standard colors in map
  mapPrimary: colorTokens.purple300,
  mapCoworkingArea: colorTokens.fuscia500,

  // Background for main content panes
  mainContent: colorTokens.gray50,
} as const satisfies GatherDesignSystemColors['bg'];

const fg = {
  // Standard foreground colors; will resolve to light or dark dependent on appearance setting
  primary: colorTokens.alphaBlack90,
  primaryDisabled: colorTokens.alphaBlack30,
  secondary: colorTokens.alphaBlack80,
  tertiary: colorTokens.alphaBlack60,
  quaternary: colorTokens.alphaBlack40,

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
  successPrimary: colorTokens.green600,
  successSecondary: colorTokens.green300,

  warningPrimary: colorTokens.orange500,
  warningSecondary: colorTokens.orange300,

  dangerPrimary: colorTokens.red600,
  dangerSecondary: colorTokens.red400,
  dangerDisabled: asColorToken(colorWithAlpha(colorTokens.red600, 0.3)),
  primaryOnDanger: colorTokens.red50,
  disabledOnDanger: colorTokens.alphaWhite80,

  // Accent foreground colors
  accentPrimary: colorTokens.blue600,
  accentSecondary: colorTokens.blue400,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.3)),
  disabledOnAccent: colorTokens.alphaWhite50,

  // Handraise foreground colors
  handraisePrimary: colorTokens.yellow400,
  handraiseSecondary: colorTokens.yellow200,
} as const satisfies GatherDesignSystemColors['fg'];

const border = {
  // Standard border colors; will resolve to light or dark dependent on appearance setting
  // [TODO] need to add pure black border
  primary: colorTokens.gray400,
  primaryDisabled: colorTokens.alphaWhite2,
  secondary: colorTokens.gray300,
  secondaryDisabled: asColorToken(colorWithAlpha(colorTokens.gray300, 0.4)),
  tertiary: colorTokens.alphaBlack10,
  quaternary: colorTokens.alphaBlack5,

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
  accentPrimary: colorTokens.blue600,
  accentSecondary: asColorToken(colorWithAlpha(colorTokens.blue600, 0.5)),
  accentTertiary: colorTokens.blue100,
  accentDisabled: asColorToken(colorWithAlpha(colorTokens.blue600, 0.2)),

  // Status border colors
  successPrimary: colorTokens.green600,
  successSecondary: colorTokens.green200,
  successTertiary: colorTokens.green100,

  warningPrimary: colorTokens.orange500,
  warningSecondary: colorTokens.orange200,
  warningTertiary: colorTokens.orange100,

  dangerPrimary: colorTokens.red600,
  dangerSecondary: colorTokens.red200,
  dangerTertiary: colorTokens.red100,

  // Ambient border colors
  ambientPrimary: colorTokens.fuscia400,
  ambientSecondary: colorTokens.fuscia300,
  ambientTertiary: colorTokens.fuscia200,
} as const satisfies GatherDesignSystemColors['border'];

// [TODO] need to add handraise & possibly the active speaker (??) border colors
const shadow = {
  inner: colorTokens.alphaWhite30,

  focusPrimary: colorTokens.alphaBlack3,
  focusAccent: asColorToken(colorWithAlpha(colorTokens.blue600, 0.2)),
  focusDanger: asColorToken(colorWithAlpha(colorTokens.red500, 0.2)),
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
  mentionText: text.accentPrimary,
  mentionBg: asColorToken(colorWithAlpha(text.accentPrimary, 0.16)),
  highlightedMentionText: colorTokens.teal700,
  highlightedMentionBg: asColorToken(colorWithAlpha(colorTokens.teal700, 0.16)),
  inlineCodeText: colorTokens.orange500,
  messageHighlightBg: asColorToken(colorWithAlpha(colorTokens.yellow600, 0.08)),
  selectedReactionBg: asColorToken(colorWithAlpha(colorTokens.teal700, 0.16)),
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

export const lightMode = {
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
