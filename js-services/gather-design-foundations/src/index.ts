// This barrel export is a special exception for consistency with gather-design-system
// See this PR for more details: https://github.com/gathertown/gather-town-v2/pull/1794
import { blurTokens } from './tokens/blur';
import { borderRadiusTokens } from './tokens/borderRadius';
import { boxShadowTokens } from './tokens/boxShadow';
import { fontSizeTokens } from './tokens/fontSize';
import { fontWeightTokens } from './tokens/fontWeight';
import {
  convertNumberTokensToStrings,
  convertPxTokensToNumberPixels,
  convertRemTokensToNumberPixels,
} from './tokens/mobileHelpers';
import { negativeScaleTokens, scaleTokens } from './tokens/scale';

// `theme` is used to access theme colors from within components
// This file must have a .css.ts extension in order for createThemeContract() to work
// TODO(ds): Mark `theme` as deprecated and update references to use `colors` instead
export { colors as theme } from './colors/colorContract.css';
// `colors` is the new name for `theme`
export { colors } from './colors/colorContract.css';

// `tokens` is used to access token values from within components
export const tokens = {
  fontSize: fontSizeTokens,
  fontWeight: fontWeightTokens,
  scale: scaleTokens,
  negativeScale: negativeScaleTokens,
  borderRadius: borderRadiusTokens,
  boxShadow: boxShadowTokens,
  blur: blurTokens,
};

// We have a separate set of tokens for mobile since React Native takes in different formats (e.g.
// numbers for pixel values instead of strings with "px" or "rem").
export const mobileTokens = {
  fontSize: convertRemTokensToNumberPixels(fontSizeTokens),
  fontWeight: convertNumberTokensToStrings(fontWeightTokens),
  scale: convertPxTokensToNumberPixels(scaleTokens),
  negativeScale: convertPxTokensToNumberPixels(negativeScaleTokens),
  borderRadius: convertPxTokensToNumberPixels(borderRadiusTokens),
};

// Appearance enum for light/dark mode
export enum Appearance {
  Light = 'light',
  Dark = 'dark',
}

export { darkMode } from './colors/darkMode';
export { lightMode } from './colors/lightMode';

// UI themes (e.g. modern, etc.)
export { type GatherTheme, Theme, themes } from './themes';
export { uiTheme } from './themes/themeContract.css';

// Types & helpers
export type { GatherDesignSystemColors } from './colors/colorContract.css';
export type { ColorToken } from './tokens/typeHelpers';
export { asColorToken } from './tokens/typeHelpers';
