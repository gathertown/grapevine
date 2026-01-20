import { style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';

export const buttonRecipe = recipe({
  base: {
    alignItems: 'center',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    fontFamily: 'inherit',
    gap: tokens.scale[4],
    justifyContent: 'center',
    position: 'relative',
    transitionDuration: '100ms',
    transitionProperty: 'transform, opacity, background-color, color',
    transitionTimingFunction: 'ease-in-out',
    userSelect: 'none',
    overflow: 'hidden',
    flexShrink: 0,

    selectors: {
      ['&:after']: {
        content: '',
        position: 'absolute',
        inset: 0,
        borderRadius: 'inherit',
        transitionProperty: 'transform, opacity, background-color, color',
        transitionDuration: '100ms',
        transitionTimingFunction: 'ease-in-out',
      },
      ['&:disabled']: {
        cursor: 'default',
        pointerEvents: 'none',
      },
      // allow hover events for tooltips on disabled buttons, but prevent clicks
      ['&:disabled[data-tooltip]']: {
        pointerEvents: 'auto',
      },
      ['&:disabled[data-tooltip]:active']: {
        pointerEvents: 'none',
      },
      ['&:active:not(:disabled)']: {
        textShadow: 'none',
        transform: 'scale(0.98)',
      },
      ['&:active:not(:disabled):after']: {
        opacity: 0,
      },
    },
  },
  variants: {
    kind: {
      primary: {
        color: theme.text.primaryOnDark,
        backgroundColor: theme.bg.accentPrimary,

        selectors: {
          ['&:after']: {
            boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset, 0px 0px 0px 1px ${theme.border.quaternary} inset`,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.accentPrimaryHover,
          },
          ['&:disabled']: {
            backgroundColor: theme.bg.accentDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.primaryDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusAccent}`,
          },
        },
      },
      secondary: {
        color: theme.text.secondary,
        backgroundColor: theme.bg.secondary,

        selectors: {
          ['&:after']: {
            boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset, 0px 0px 0px 1px ${theme.border.quaternary} inset`,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.secondaryHover,
          },
          ['&:disabled']: {
            color: theme.text.primaryDisabled,
            backgroundColor: theme.bg.secondaryDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.secondaryDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusPrimary}`,
          },
        },
      },
      danger: {
        color: theme.text.primaryOnDanger,
        backgroundColor: theme.bg.dangerPrimary,

        selectors: {
          ['&:after']: {
            boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset, 0px 0px 0px 1px ${theme.border.quaternary} inset`,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.dangerPrimaryHover,
          },
          ['&:disabled']: {
            backgroundColor: theme.bg.dangerDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.primaryDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusDanger}`,
          },
        },
      },
      dangerSecondary: {
        color: theme.text.dangerPrimary,
        backgroundColor: theme.bg.secondary,

        selectors: {
          ['&:after']: {
            boxShadow: `0px 1px 2px 0px ${theme.shadow.inner} inset, 0px 0px 0px 1px ${theme.border.quaternary} inset`,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.dangerTertiary,
          },
          ['&:disabled']: {
            backgroundColor: theme.bg.dangerDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.primaryDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusPrimary}`,
          },
        },
      },
      outlinePrimary: {
        color: theme.text.accentPrimary,
        backgroundColor: 'transparent',

        selectors: {
          ['&:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.accentSecondary} inset`,
          },
          ['&:active:not(:disabled):after']: {
            opacity: 1,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.accentSecondaryHover,
          },
          ['&:disabled']: {
            color: theme.text.accentDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.accentDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusAccent}`,
          },
        },
      },
      outlineSecondary: {
        color: theme.text.secondary,
        backgroundColor: 'transparent',

        selectors: {
          ['&:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.secondary} inset`,
          },
          ['&:active:not(:disabled):after']: {
            opacity: 1,
          },
          ['&:hover']: {
            backgroundColor: theme.bg.tertiaryHover,
          },
          ['&:disabled']: {
            color: theme.text.primaryDisabled,
          },
          ['&:disabled:after']: {
            boxShadow: `0px 0px 0px 1px ${theme.border.secondaryDisabled} inset`,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusPrimary}`,
          },
        },
      },
      transparent: {
        color: theme.text.secondary,
        backgroundColor: 'transparent',

        selectors: {
          ['&:hover']: {
            backgroundColor: theme.bg.tertiaryHover,
          },
          ['&:disabled']: {
            color: theme.text.primaryDisabled,
          },
          ['&:focus-visible']: {
            boxShadow: `0px 0px 0px 3px ${theme.shadow.focusPrimary}`,
          },
        },
      },
    },
    size: {
      xs: {
        borderRadius: tokens.borderRadius[8],
        height: tokens.scale[24],
        padding: `${tokens.scale[4]} ${tokens.scale[6]}`,
      },
      sm: {
        borderRadius: tokens.borderRadius[8],
        height: tokens.scale[28],
        padding: `${tokens.scale[6]} ${tokens.scale[8]}`,
      },
      md: {
        borderRadius: tokens.borderRadius[10],
        height: tokens.scale[32],
        padding: `${tokens.scale[6]} ${tokens.scale[10]}`,
      },
      lg: {
        borderRadius: tokens.borderRadius[10],
        height: tokens.scale[36],
        padding: `${tokens.scale[8]} ${tokens.scale[12]}`,
      },
    },
    fullWidth: {
      true: {
        flexGrow: 1,
      },
    },
    iconOnly: {
      true: {
        aspectRatio: '1/1',
        padding: 0,
      },
    },
  },
  defaultVariants: {
    size: 'md',
    kind: 'primary',
    fullWidth: false,
    iconOnly: false,
  },
});

export const buttonTextStyle = style({
  display: 'inline-block',
  fontWeight: tokens.fontWeight.bold,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',

  selectors: {
    [`${buttonRecipe.classNames.variants.size.xs} &`]: {
      fontSize: tokens.fontSize.xs,
      fontWeight: tokens.fontWeight.medium,
      lineHeight: '0.875rem',
      padding: `0 ${tokens.scale[2]}`,
    },
    [`${buttonRecipe.classNames.variants.size.sm} &`]: {
      fontSize: tokens.fontSize.sm,
      fontWeight: tokens.fontWeight.medium,
      lineHeight: '0.875rem',
      padding: `0 ${tokens.scale[2]}`,
    },
    [`${buttonRecipe.classNames.variants.size.md} &`]: {
      fontSize: tokens.fontSize.sm,
      fontWeight: tokens.fontWeight.medium,
      lineHeight: '1rem',
      padding: `0 ${tokens.scale[4]}`,
    },
    [`${buttonRecipe.classNames.variants.size.lg} &`]: {
      fontSize: tokens.fontSize.md,
      fontWeight: tokens.fontWeight.medium,
      lineHeight: '1rem',
      padding: `0 ${tokens.scale[8]}`,
    },
  },
});

export const buttonContentRecipe = recipe({
  base: {
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  variants: {
    fullWidth: {
      true: {
        width: '100%',
      },
    },
    loading: {
      true: {
        visibility: 'hidden',
      },
    },
  },
  defaultVariants: {
    loading: false,
  },
});

export type ButtonVariants = RecipeVariants<typeof buttonRecipe>;
