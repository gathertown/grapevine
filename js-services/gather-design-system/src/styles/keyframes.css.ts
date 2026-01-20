import { keyframes } from '@vanilla-extract/css';

export const spinKeyframes = keyframes({
  from: {
    transform: 'rotate(0deg)',
  },
  to: {
    transform: 'rotate(360deg)',
  },
});

export const fadeInKeyframes = keyframes({
  from: {
    opacity: 0,
  },
  to: {
    opacity: 1,
  },
});

export const fadeOutKeyframes = keyframes({
  from: {
    opacity: 1,
  },
  to: {
    opacity: 0,
  },
});
