import { style, StyleRule } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

const badgeBaseStyle = style({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  gap: tokens.scale[4],
  width: 'auto',
});

type ColorKey = 'light-gray' | 'gray' | 'success' | 'warning' | 'danger' | 'accent';
const colorKeys: ColorKey[] = ['light-gray', 'gray', 'success', 'warning', 'danger', 'accent'];

const fillStyles: Record<ColorKey, StyleRule> = {
  'light-gray': {
    backgroundColor: theme.bg.tertiaryTransparentDark,
    borderColor: theme.border.secondary,
  },
  gray: {
    backgroundColor: theme.bg.secondary,
    borderColor: theme.border.quaternary,
  },
  success: {
    backgroundColor: theme.bg.successTertiary,
    borderColor: theme.border.successTertiary,
  },
  warning: {
    backgroundColor: theme.bg.warningTertiary,
    borderColor: theme.border.warningTertiary,
  },
  danger: {
    backgroundColor: theme.bg.dangerTertiary,
    borderColor: theme.border.dangerTertiary,
  },
  accent: {
    backgroundColor: theme.bg.accentTertiary,
    borderColor: theme.border.accentTertiary,
  },
};
const outlineStyles: Record<ColorKey, StyleRule> = {
  'light-gray': {
    color: theme.text.quaternary,
    borderColor: theme.border.secondary,
  },
  gray: {
    color: theme.text.tertiary,
    borderColor: theme.border.tertiary,
  },
  success: {
    borderColor: theme.border.successSecondary,
  },
  warning: {
    borderColor: theme.border.warningPrimary,
  },
  danger: {
    borderColor: theme.border.dangerPrimary,
  },
  accent: {
    borderColor: theme.border.accentPrimary,
  },
};

const fillCompoundVariants = colorKeys.map((color) => ({
  variants: { kind: 'fill' as const, color },
  style: fillStyles[color],
}));

const outlineCompoundVariants = colorKeys.map((color) => ({
  variants: { kind: 'outline' as const, color },
  style: outlineStyles[color],
}));

export const badgeRecipe = recipe({
  base: badgeBaseStyle,
  variants: {
    kind: {
      fill: {
        boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset`,
        border: `${tokens.scale[1]} solid transparent`,
      },
      outline: {
        border: `${tokens.scale[1]} solid transparent`,
      },
    },
    color: {
      'light-gray': {
        color: theme.text.quaternary,
      },
      gray: {
        color: theme.text.tertiary,
      },
      success: {
        color: theme.text.successPrimary,
      },
      warning: {
        color: theme.text.warningPrimary,
      },
      danger: {
        color: theme.text.dangerPrimary,
      },
      accent: {
        color: theme.text.accentPrimary,
      },
    },
    size: {
      sm: {
        padding: `${tokens.scale[0]} ${tokens.scale[4]}`,
        height: tokens.scale[18],
        minWidth: tokens.scale[18],
        borderRadius: tokens.borderRadius.full,
      },
      md: {
        padding: `${tokens.scale[0]} ${tokens.scale[6]}`,
        height: tokens.scale[20],
        minWidth: tokens.scale[20],
        borderRadius: tokens.borderRadius.full,
      },
      'sm-square': {
        padding: '3px',
        height: '20px',
        minWidth: '20px',
        borderRadius: tokens.borderRadius[6],
      },
    },
  },
  compoundVariants: [...fillCompoundVariants, ...outlineCompoundVariants],
  defaultVariants: {
    kind: 'fill',
    color: 'gray',
    size: 'md',
  },
});

export const badgeTextStyle = style({
  display: 'inline-block',
  whiteSpace: 'nowrap',
  textOverflow: 'ellipsis',

  selectors: {
    [`${badgeRecipe.classNames.variants.size.md} &`]: {
      fontSize: tokens.fontSize.xs,
      fontWeight: tokens.fontWeight.medium,
    },
    [`${badgeRecipe.classNames.variants.size.sm} &`]: {
      fontSize: tokens.fontSize.xxs,
      fontWeight: tokens.fontWeight.semibold,
    },
    [`${badgeRecipe.classNames.variants.size['sm-square']} &`]: {
      fontSize: tokens.fontSize.xxs,
      fontWeight: tokens.fontWeight.medium,
    },
  },
});

export type BadgeVariants = RecipeVariants<typeof badgeRecipe>;
