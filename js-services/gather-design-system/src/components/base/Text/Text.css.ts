import { style, styleVariants } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const textBaseStyle = style({
  margin: 0,
  padding: 0,
});

export const textColorStyles = {
  emoji: style({ color: 'black' }),
  inherit: style({ color: 'inherit' }),
  ...styleVariants(theme.text, (color) => ({
    color,
  })),
  ...styleVariants(theme.presence, (color) => ({
    color,
  })),
};

const textDecorationBaseStyle = style({
  textDecorationLine: 'underline',
});

const textDecorationStyles = styleVariants({
  solid: [textDecorationBaseStyle, { textDecorationStyle: 'solid' }],
  double: [textDecorationBaseStyle, { textDecorationStyle: 'double' }],
  dotted: [textDecorationBaseStyle, { textDecorationStyle: 'dotted' }],
  dashed: [textDecorationBaseStyle, { textDecorationStyle: 'dashed' }],
  wavy: [textDecorationBaseStyle, { textDecorationStyle: 'wavy' }],
});

export const fontWeightStyles = {
  inherit: style({ fontWeight: 'inherit' }),
  ...styleVariants(tokens.fontWeight, (fontWeight) => ({
    fontWeight,
  })),
};

const fontSizeStyles = {
  inherit: {
    fontSize: 'inherit',
    lineHeight: 'inherit',
  },
  xxxs: {
    fontSize: tokens.fontSize.xxxs,
    lineHeight: '0.75rem',
  },
  xxs: {
    fontSize: tokens.fontSize.xxs,
    lineHeight: '0.75rem',
  },
  xs: {
    fontSize: tokens.fontSize.xs,
    lineHeight: '0.875rem',
  },
  sm: {
    fontSize: tokens.fontSize.sm,
    lineHeight: '1rem',
  },
  md: {
    fontSize: tokens.fontSize.md,
    lineHeight: '1.25rem',
  },
  lg: {
    fontSize: tokens.fontSize.lg,
    lineHeight: '1.5rem',
  },
  xl: {
    fontSize: tokens.fontSize.xl,
    lineHeight: '1.75rem',
  },
  xxl: {
    fontSize: tokens.fontSize.xxl,
    lineHeight: '2rem',
  },
};

const lineHeightStyles = {
  inherit: {
    lineHeight: 'inherit',
  },
};

export const textRecipe = recipe({
  base: textBaseStyle,
  variants: {
    color: textColorStyles,
    fontSize: fontSizeStyles,
    fontWeight: fontWeightStyles,
    textAlign: {
      left: { textAlign: 'left' },
      center: { textAlign: 'center' },
      right: { textAlign: 'right' },
      justify: { textAlign: 'justify' },
    },
    textWrap: {
      wrap: { textWrap: 'wrap' },
      nowrap: { textWrap: 'nowrap' },
      pretty: { textWrap: 'pretty' },
      balance: { textWrap: 'balance' },
    },
    wordBreak: {
      normal: { wordBreak: 'normal' },
      breakAll: { wordBreak: 'break-all' },
      keepAll: { wordBreak: 'keep-all' },
      breakWord: { wordBreak: 'break-word' },
    },
    textDecorationStyle: textDecorationStyles,
    truncate: {
      true: {
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        maxWidth: '100%',
      },
    },
    selectable: {
      true: {
        userSelect: 'auto',
      },
      false: {
        userSelect: 'none',
      },
    },
    textTransform: {
      capitalize: {
        textTransform: 'capitalize',
      },
      uppercase: {
        textTransform: 'uppercase',
      },
      lowercase: {
        textTransform: 'lowercase',
      },
    },
    lineHeight: lineHeightStyles,
    flexShrink: {
      inherit: { flexShrink: 'inherit' },
      0: { flexShrink: 0 },
      1: { flexShrink: 1 },
      2: { flexShrink: 2 },
    },
    display: {
      block: { display: 'block' },
    },
    fontStyle: {
      italic: { fontStyle: 'italic' },
    },
  },
  defaultVariants: {
    truncate: false,
    fontWeight: 'inherit',
    textWrap: 'wrap',
    fontSize: 'md',
  },
});

export type TextVariants = RecipeVariants<typeof textRecipe>;
