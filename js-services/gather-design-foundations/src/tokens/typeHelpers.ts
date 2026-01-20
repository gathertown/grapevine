import { Tagged } from 'type-fest';

export type ColorToken = Tagged<string, 'ColorToken'>;

// We intentionally cast to a color token.
// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const asColorToken = (value: string): ColorToken => value as ColorToken;
