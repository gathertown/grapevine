import { createThemeContract } from '@vanilla-extract/css';

export const themeContract = {
  bodyGradientStartColor: '',
  bodyGradientEndColor: '',
  sidebarGradientStartColor: '',
  sidebarGradientEndColor: '',
  noiseOpacity: '',
};

export const uiTheme = createThemeContract(themeContract);

export type GatherTheme = typeof themeContract;
