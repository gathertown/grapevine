import { createTheme, style } from '@vanilla-extract/css';

import {
  Appearance,
  colors,
  darkMode,
  lightMode,
  themes,
  uiTheme,
} from '@gathertown/gather-design-foundations';

const lightModeClass = createTheme(colors, lightMode);
const darkModeClass = createTheme(colors, darkMode);

export const colorMode = {
  [Appearance.Light]: lightModeClass,
  [Appearance.Dark]: darkModeClass,
};

// Dynamically create a class for each theme/appearance permutation
export const themeClasses = Object.fromEntries(
  Object.entries(themes).map(([name, theme]) => [
    name,
    {
      [Appearance.Light]: createTheme(uiTheme, theme.light),
      [Appearance.Dark]: createTheme(uiTheme, theme.dark),
    },
  ])
) satisfies Record<string, Record<Appearance, unknown>>;

// Ensure at least one theme exists
if (Object.keys(themeClasses).length === 0)
  throw new Error('At least one theme must be defined in gather-design-foundations');

export const baseStyle = style({
  color: colors.text.primary,
});
