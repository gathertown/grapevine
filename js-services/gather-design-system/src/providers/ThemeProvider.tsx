import React, { useEffect, useMemo } from 'react';

import { Logger } from '../utils/logger';
import { Appearance, Theme } from '@gathertown/gather-design-foundations';
import { cx } from '../helpers/classnames';
import { baseStyle, colorMode, themeClasses } from './ThemeProvider.css';

type ThemeProviderProps = {
  children: React.ReactNode;
  appearance?: Appearance;
  theme?: keyof typeof themeClasses;
  className?: string;
};

// Currently this is duplicated in AppearanceSettingsRepo.ts
// TODO [VW-4439]: Consolidate enums
export enum AppearanceSetting {
  Light = 'light',
  System = 'system',
  Dark = 'dark',
}

const DEFAULT_THEME = Theme.Modern;
const DEFAULT_APPEARANCE = Appearance.Light;

const getPreferredAppearance = (): Appearance | undefined => {
  if (typeof window === 'undefined') return undefined;

  try {
    const preference = window.localStorage.getItem('appearance-setting');

    if (!preference) return undefined;

    // LocalStorageService serializes all values, so we need to parse them back to their original type
    const parsedPreference = JSON.parse(preference);

    if (parsedPreference === AppearanceSetting.Dark) return Appearance.Dark;
    if (parsedPreference === AppearanceSetting.Light) return Appearance.Light;

    if (parsedPreference === AppearanceSetting.System && window.matchMedia) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
      return prefersDark.matches ? Appearance.Dark : Appearance.Light;
    }
  } catch (error) {
    Logger.error('Error getting preferred appearance', { error });
  }

  return undefined;
};

export const ThemeProvider: React.FC<ThemeProviderProps> = React.memo(function ThemeProvider({
  children,
  appearance,
  className,
  theme = DEFAULT_THEME,
}) {
  // Use provided appearance or detect from user preference
  const resolvedAppearance = useMemo(() => {
    if (appearance) return appearance;
    return getPreferredAppearance() ?? DEFAULT_APPEARANCE;
  }, [appearance]);

  const themeData = themeClasses[theme];

  if (!themeData) {
    Logger.error(`Error: Theme "${theme}" not found in themeClasses`);
  }

  const lightThemeClass: string = themeData?.[Appearance.Light] ?? '';
  const darkThemeClass: string = themeData?.[Appearance.Dark] ?? '';

  useEffect(() => {
    if (themeData) {
      document.documentElement.classList.remove(darkThemeClass, lightThemeClass);
      document.documentElement.classList.add(themeData[resolvedAppearance]);
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedAppearance, themeData]);

  return (
    <div
      className={cx(colorMode[resolvedAppearance], baseStyle, className)}
      style={{ display: 'contents' }}
    >
      {children}
    </div>
  );
});
