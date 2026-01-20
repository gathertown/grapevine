import { globalStyle, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const messageEditorContainerRecipe = recipe({
  base: {
    overflow: 'auto',
  },
  variants: {
    showActionsInline: {
      true: {
        margin: `${tokens.scale[4]} 0 ${tokens.scale[4]} 0`,
      },
      false: {
        margin: `${tokens.scale[4]} ${tokens.scale[8]} ${tokens.scale[4]} ${tokens.scale[8]}`,
      },
    },
  },
});

export const messageContentStyle = style({
  fontSize: tokens.fontSize.md,
  // TODO [DES-2723]: Support multiline <Text /> with better line height
  lineHeight: '1.375rem',
  overflowWrap: 'break-word',
  wordBreak: 'normal',
});

export const messageContentStyleCollapsedPadding = style({});

globalStyle(`${messageContentStyleCollapsedPadding} p`, {
  margin: '0 !important',
});

globalStyle(`${messageContentStyle} p`, {
  margin: `${tokens.scale[8]} 0`,
  lineHeight: '1.375rem',
});

globalStyle(`${messageContentStyle} p.is-editor-empty:first-child`, {
  position: 'relative',
});

globalStyle(`${messageContentStyle} p.is-editor-empty:first-child::before`, {
  color: theme.text.quaternary,
  content: 'attr(data-placeholder)',
  pointerEvents: 'none',
  position: 'absolute',
  top: 0,
  left: 0,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  maxWidth: '100%',
});

globalStyle(`${messageContentStyle} strong`, {
  fontWeight: tokens.fontWeight.bold,
});

globalStyle(`${messageContentStyle} em`, {
  fontStyle: 'italic',
});

globalStyle(`${messageContentStyle} code`, {
  backgroundColor: theme.bg.tertiaryTransparentLight,
  color: theme.chat.inlineCodeText,
  border: `1px solid ${theme.border.tertiary}`,
  borderRadius: tokens.borderRadius[4],
  fontFamily: 'monospace',
  fontSize: tokens.fontSize.sm,
  padding: tokens.scale[2],
  display: 'inline',
  whiteSpace: 'pre-wrap',
  wordWrap: 'break-word',
  wordBreak: 'break-word',
});

globalStyle(`${messageContentStyle} pre`, {
  fontFamily: 'monospace',
  padding: tokens.scale[4],
  margin: `${tokens.scale[8]} 0`,
  borderRadius: tokens.borderRadius[4],
  border: `1px solid ${theme.border.tertiary}`,
  backgroundColor: 'transparent',
  fontSize: tokens.fontSize.sm,
  lineHeight: tokens.fontSize.md,
});

globalStyle(`${messageContentStyle} pre code`, {
  display: 'inline-block',
  border: 'none',
  backgroundColor: 'transparent',
  color: theme.text.primary,
  // Don't let text go off the screen (or force scrolling)
  wordBreak: 'break-all',
});

globalStyle(`${messageContentStyle} blockquote`, {
  borderLeft: `4px solid ${theme.border.tertiary}`,
  padding: `${tokens.scale[1]} ${tokens.scale[12]}`,
  margin: `${tokens.scale[8]} 0`,
  color: theme.text.primary,
});

globalStyle(`${messageContentStyle} > ul`, {
  margin: `${tokens.scale[8]} 0`,
  marginInlineStart: tokens.scale[8],
});

globalStyle(`${messageContentStyle} ul p, ${messageContentStyle} li p`, {
  margin: `${tokens.scale[6]} 0`,
});

globalStyle(`${messageContentStyle} ul`, {
  paddingInlineStart: tokens.scale[16],
  listStyleType: 'disc',
});

globalStyle(`${messageContentStyle} ul ul`, {
  listStyleType: 'circle',
});

globalStyle(`${messageContentStyle} ul ul ul`, {
  listStyleType: 'square',
});

globalStyle(`${messageContentStyle} ul ul ul ul`, {
  listStyleType: 'disc',
});

globalStyle(`${messageContentStyle} ul ul ul ul ul`, {
  listStyleType: 'circle',
});

globalStyle(`${messageContentStyle} ul ul ul ul ul ul`, {
  listStyleType: 'square',
});

globalStyle(`${messageContentStyle} > ol`, {
  margin: `${tokens.scale[8]} 0`,
  marginInlineStart: tokens.scale[8],
});

globalStyle(`${messageContentStyle} ol`, {
  paddingInlineStart: tokens.scale[16],
  listStyleType: 'decimal',
});

globalStyle(`${messageContentStyle} ol > li`, {
  marginInlineStart: tokens.scale[8],
});

globalStyle(`${messageContentStyle} li`, {});

globalStyle(`${messageContentStyle} a`, {
  color: theme.text.accentSecondary,
});
