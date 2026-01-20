import { globalStyle, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const transientMessageEditorContainerBaseStyle = style({
  border: `1px solid ${theme.border.secondary}`,
  color: theme.text.primary,
  width: '100%',
  position: 'relative',
  backgroundColor: 'rgba(255, 255, 255, 0.03)',
  borderRadius: tokens.borderRadius[10],
  padding: `${tokens.scale[10]} ${tokens.scale[10]} ${tokens.scale[8]} ${tokens.scale[36]}`,
  fontSize: tokens.fontSize.sm,
  lineHeight: tokens.fontSize.md,
});

export const transientMessageEditorContainerRecipe = recipe({
  base: transientMessageEditorContainerBaseStyle,
  variants: {
    hasMentions: {
      true: {
        backgroundColor: `color-mix(in srgb, ${theme.fg.handraisePrimary} 5%, transparent)`,
        borderColor: `color-mix(in srgb, ${theme.fg.handraisePrimary} 20%, transparent)`,
        selectors: {
          '&:focus-visible': {
            borderColor: `color-mix(in srgb, ${theme.fg.handraisePrimary} 30%, transparent)`,
          },

          '&:hover': {
            borderColor: `color-mix(in srgb, ${theme.fg.handraisePrimary} 30%, transparent)`,
          },
        },
      },
      false: {
        selectors: {
          '&:focus-visible': {
            borderColor: theme.border.primary,
          },

          '&:hover': {
            borderColor: theme.border.primary,
          },
        },
      },
    },
  },
});

globalStyle(`${transientMessageEditorContainerBaseStyle} p`, {
  fontSize: tokens.fontSize.sm,
  lineHeight: tokens.fontSize.md,
  overflowWrap: 'break-word',
  wordBreak: 'normal',
});

globalStyle(`${transientMessageEditorContainerBaseStyle} p.is-editor-empty:first-child`, {
  position: 'relative',
});

globalStyle(`${transientMessageEditorContainerBaseStyle} p.is-editor-empty:first-child::before`, {
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

export const transientMentionStyle = style({
  appearance: 'none',
  display: 'inline',
  border: `1px solid color-mix(in srgb, ${theme.fg.handraisePrimary} 20%, transparent)`,
  borderRadius: tokens.borderRadius[4],
  padding: `${tokens.scale[2]} ${tokens.scale[4]}`,
  backgroundColor: `color-mix(in srgb, ${theme.fg.handraisePrimary} 5%, transparent)`,
  color: `color-mix(in srgb, ${theme.fg.handraisePrimary} 80%, transparent)`,
  fontSize: tokens.fontSize.sm,
  lineHeight: tokens.fontSize.md,
});
