import classNames from 'classnames';
import React from 'react';
import { isMacOs } from 'react-device-detect';

import { Flex } from '../../layout/Flex/Flex';
import { OverrideStyleProps } from '../../layout/layoutTypes';
import { hotkeyRecipe, specialKeyStyle } from './KeyboardShortcut.css';
import type { KeyboardKey, KnownModifierKeys } from './KeyboardTypes';

export type GenericKeyboardKey = Exclude<KeyboardKey, 'Command' | 'Control'> | 'Meta' | string;
type Platform = 'mac' | 'windows';

export type KeyboardShortcutProps = {
  /**
   * An array of keys representing a keyboard shortcut. ex: `["cmd", "shift", "a"]` => `⌘⇧A`
   */
  keys: readonly GenericKeyboardKey[];
  display?: 'none' | 'flex' | 'inline-flex' | undefined;
  platform?: Platform;
  size?: 'sm' | 'md';
} & Partial<OverrideStyleProps>;

/**
 * Map "known" modifier keys to special strings
 */
const MODIFIER_KEY_ICON_MAP: Record<KnownModifierKeys, string> = {
  Command: '⌘',
  Option: '⌥',
  Alt: 'alt',
  Control: '⌃',
  Shift: '⇧',
  Enter: '↵',
  Return: '↵',
};

const GENERIC_KEY_ICON_MAP: Partial<Record<GenericKeyboardKey, string>> = {
  ArrowUp: '↑',
  ArrowDown: '↓',
  ArrowLeft: '↑',
  ArrowRight: '→',
};

const isModifierKey = (key: GenericKeyboardKey): key is GenericKeyboardKey & KnownModifierKeys =>
  Object.hasOwn(MODIFIER_KEY_ICON_MAP, key);

const asModifierKey = (key: GenericKeyboardKey): KnownModifierKeys | null => {
  if (key === 'Meta') return isMacOs ? 'Command' : 'Control';

  return isModifierKey(key) ? key : null;
};

const getSpecialKeyString = (key: GenericKeyboardKey): string | null => {
  const modifierKey = asModifierKey(key);
  if (modifierKey) return MODIFIER_KEY_ICON_MAP[modifierKey];
  return GENERIC_KEY_ICON_MAP[key] ?? null;
};

export const KeyboardShortcut = React.memo(function KeyboardShortcut({
  keys,
  display = 'inline-flex',
  platform,
  size = 'md',
  style,
}: KeyboardShortcutProps) {
  const resolvedPlatform = platform ?? (isMacOs ? 'mac' : 'windows');
  return (
    <Flex align="center" display={display} style={{ gap: 3 }}>
      {keys.map((key, index) => {
        if (key === 'Meta' && resolvedPlatform === 'windows') {
          return (
            <kbd key={index} className={hotkeyRecipe({ size })} style={style}>
              Ctrl
            </kbd>
          );
        }

        const specialKey = getSpecialKeyString(key);
        return (
          <kbd
            key={index}
            className={classNames(hotkeyRecipe({ size }), { [specialKeyStyle]: specialKey })}
            style={style}
          >
            {specialKey ?? key}
          </kbd>
        );
      })}
    </Flex>
  );
});
