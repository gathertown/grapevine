import { keyframes, style } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { theme, tokens } from '@gathertown/gather-design-foundations';
import { fadeInKeyframes, fadeOutKeyframes } from '../../../styles/keyframes.css';
import { disabledAnimations } from '../../../styles/reusableStyles.css';

// TODO(ds) [APP-8833]: Abstract animation durations into semantic tokens

export const overlayStyle = recipe({
  base: {
    animationDuration: '200ms',
    animationFillMode: 'forwards',
    animationName: fadeInKeyframes,
    animationTimingFunction: 'ease-out',
    backgroundColor: theme.ui.modalOverlay,
    inset: 0,
    transitionDuration: '200ms',
    transitionProperty: 'opacity',
    transitionTimingFunction: 'ease-out',
    selectors: {
      "&[data-state='closed']": {
        animationDuration: '150ms',
        animationFillMode: 'forwards',
        animationName: fadeOutKeyframes,
        animationTimingFunction: 'ease-out',
      },
    },
  },
  variants: {
    shouldFitToPortalContainer: {
      true: {
        position: 'absolute',
      },
      false: {
        position: 'fixed',
      },
    },
  },
});

const modalEnterKeyframes = keyframes({
  from: {
    opacity: 0,
    transform: `translate(-50%, calc(-50% + ${tokens.scale[16]}))`,
  },
  to: {
    opacity: 1,
    transform: 'translate(-50%, -50%)',
  },
});

const modalExitKeyframes = keyframes({
  from: {
    opacity: 1,
    transform: 'translate(-50%, -50%)',
  },
  to: {
    opacity: 0,
    transform: `translate(-50%, calc(-50% + ${tokens.scale[8]}))`,
  },
});

const cmdkEnterKeyframes = keyframes({
  from: {
    opacity: 0,
    transform: `translateX(-50%) scale(0.96)`,
  },
  to: {
    opacity: 1,
    transform: 'translateX(-50%) scale(1)',
  },
});

const modalBase = style({
  animationDelay: '50ms',
  animationDuration: '100ms',
  animationFillMode: 'forwards',
  animationName: modalEnterKeyframes,
  animationTimingFunction: 'ease',
  backgroundColor: theme.bg.primary,
  borderRadius: tokens.borderRadius[12],
  boxShadow: tokens.boxShadow.xl,
  color: theme.text.primary,
  display: 'flex',
  flexDirection: 'column',
  left: '50%',
  opacity: 0,
  overflow: 'scroll',
  top: '50%',
  willChange: 'opacity, transform',

  // TODO(ds) [APP-9194]: Create common scrollbar styles
  scrollbarWidth: 'none',
  msOverflowStyle: 'none',
  selectors: {
    '&::-webkit-scrollbar': {
      display: 'none',
    },
    [`${disabledAnimations} &[data-state="open"]`]: {
      opacity: 1,
      transform: 'translate(-50%, -50%)',
    },
    [`${disabledAnimations} &[data-state="closed"]`]: {
      opacity: 0,
    },
    "&[data-state='closed']": {
      animationDelay: '0ms',
      animationDuration: '100ms',
      animationFillMode: 'forwards',
      animationName: modalExitKeyframes,
      animationTimingFunction: 'ease-in',
    },
  },
});

export const modalRecipe = recipe({
  base: modalBase,
  variants: {
    variant: {
      default: {
        width: '800px',
        height: '600px',
      },
      cmdk: {
        animationName: cmdkEnterKeyframes,
        animationTimingFunction: 'ease-in-out',
        maxHeight: '400px',
        overflow: 'hidden',
        padding: tokens.scale[16],
        top: `max(calc(50% - 200px), calc(200px / 2) + ${tokens.scale[24]})`,
        width: '512px',
      },
      auto: {
        width: 'auto',
        maxWidth: `calc(100% - ${tokens.scale[48]})`,
        maxHeight: `calc(100% - ${tokens.scale[48]})`,
      },
      cmdkV2: {
        animationName: cmdkEnterKeyframes,
        animationTimingFunction: 'ease-in-out',
        maxHeight: '400px',
        overflow: 'hidden',
        top: `max(calc(50% - 200px), calc(200px / 2) + ${tokens.scale[24]})`,
        width: '570px',
        border: `1px solid ${theme.border.quaternary}`,
      },
    },
    shouldFitToPortalContainer: {
      true: {
        position: 'absolute',
      },
      false: {
        position: 'fixed',
      },
    },
  },
  defaultVariants: {
    variant: 'default',
  },
});

const modalHeaderBase = style({
  backdropFilter: tokens.blur.lg,
  backgroundColor: `oklch(from ${theme.bg.primary} l c h / 0.5)`,
  borderBottom: `1px solid ${theme.border.tertiary}`,
  position: 'sticky',
  top: 0,
  flexShrink: 0,
  // Headers should be above other content, but we don't want to reorder the markup to be below the
  // content because it breaks semantic order (and screen readers and such).
  zIndex: 1,
  borderRadius: `${tokens.borderRadius[12]} ${tokens.borderRadius[12]} 0 0`,
});

export const modalHeaderRecipe = recipe({
  base: modalHeaderBase,
  variants: {
    size: {
      md: {
        padding: tokens.scale[12],
      },
      lg: {
        height: 60, // per design
        padding: `0 ${tokens.scale[12]} 0 ${tokens.scale[24]}`,
      },
    },
    noBorder: {
      true: {
        borderBottom: 'none',
      },
    },
  },
});

export const modalBodyStyle = style({
  // Create a new stacking context for the modal body.
  isolation: 'isolate',
  display: 'flex',
  flexDirection: 'column',
  padding: tokens.scale[24],
});

export const modalFooterStyle = style({
  display: 'flex',
  flexDirection: 'row',
  justifyContent: 'flex-end',
  padding: `${tokens.scale[12]} ${tokens.scale[16]}`,
  bottom: 0,
  position: 'sticky',
  backdropFilter: tokens.blur.lg,
  backgroundColor: `oklch(from ${theme.bg.primary} l c h / 0.5)`,
  borderTop: `1px solid ${theme.border.tertiary}`,
});

export type ModalRecipe = RecipeVariants<typeof modalRecipe>;
