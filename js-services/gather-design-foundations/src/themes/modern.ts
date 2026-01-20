import { GatherTheme } from './themeContract.css';

export const modernLight = {
  bodyGradientStartColor: 'hsl(0, 0%, 94%)',
  bodyGradientEndColor: 'hsl(32, 1%, 86%)',
  sidebarGradientStartColor: 'hsl(0, 0%, 100%, 0.8)',
  sidebarGradientEndColor: 'hsl(0, 0%, 100%, 0.7)',
  noiseOpacity: '0',
} as const satisfies GatherTheme;

export const modernDark = {
  bodyGradientStartColor: 'hsl(0, 0%, 9%)',
  bodyGradientEndColor: 'hsl(32, 1%, 6%)',
  sidebarGradientStartColor: 'hsl(0, 0%, 100%, 0.03)',
  sidebarGradientEndColor: 'hsl(0, 0%, 100%, 0.03)',
  noiseOpacity: '0',
} as const satisfies GatherTheme;
