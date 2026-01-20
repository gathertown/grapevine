/**
 * Modifiers that map to icons
 */
export type KnownModifierKeys =
  | 'Command'
  | 'Option'
  | 'Alt'
  | 'Control'
  | 'Shift'
  | 'Enter'
  | 'Return';

/**
 * Alphabetic keys
 */
export type AlphaKeys =
  | 'a'
  | 'b'
  | 'c'
  | 'd'
  | 'e'
  | 'f'
  | 'g'
  | 'h'
  | 'i'
  | 'j'
  | 'k'
  | 'l'
  | 'm'
  | 'n'
  | 'o'
  | 'p'
  | 'q'
  | 'r'
  | 's'
  | 't'
  | 'u'
  | 'v'
  | 'w'
  | 'x'
  | 'y'
  | 'z';

/**
 * Digits
 */
export type DigitKeys = '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9';

/**
 * Common punctuation / special characters
 */
export type PunctuationKeys =
  | ','
  | '.'
  | ';'
  | ':'
  | "'"
  | '"'
  | '`'
  | '['
  | ']'
  | '('
  | ')'
  | '{'
  | '}'
  | '<'
  | '>'
  | '/'
  | '?'
  | '!'
  | '@'
  | '#'
  | '$'
  | '%'
  | '^'
  | '&'
  | '*'
  | '-'
  | '_'
  | '+'
  | '=';

/**
 * Example of arrow keys, function keys, etc.
 */
export type SpecialKeys =
  | 'Tab'
  | 'Esc'
  | 'ArrowUp'
  | 'ArrowDown'
  | 'ArrowLeft'
  | 'ArrowRight'
  | 'Del'
  | 'F1'
  | 'F2'
  | 'F3'
  | 'F4'
  | 'F5'
  | 'F6'
  | 'F7'
  | 'F8'
  | 'F9'
  | 'F10'
  | 'F11'
  | 'F12';

/**
 * All possible keys for a keyboard shortcut
 */
export type KeyboardKey = KnownModifierKeys | AlphaKeys | DigitKeys | PunctuationKeys | SpecialKeys;
