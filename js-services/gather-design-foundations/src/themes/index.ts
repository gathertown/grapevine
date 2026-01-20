import { modernDark, modernLight } from './modern';
import { GatherTheme } from './themeContract.css';

export enum Theme {
  Modern = 'modern',
}

type ThemeVariant = {
  light: GatherTheme;
  dark: GatherTheme;
};

export const themes: Record<Theme, ThemeVariant> = {
  [Theme.Modern]: {
    light: modernLight,
    dark: modernDark,
  },
};

export { type GatherTheme };
