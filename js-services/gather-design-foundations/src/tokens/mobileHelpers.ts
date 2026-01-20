import { mapObjIndexed } from 'ramda';

import { BASE_REM_SIZE_PX } from './fontSize';

const convertNumericTokensWithSuffix = <T extends Record<string, string>>(
  tokens: T,
  suffix: string,
  converter: (value: number) => number = (x) => x
) => {
  const convertValue = (tokenValue: string) => {
    const numericValue = parseFloat(tokenValue.replace(suffix, ''));
    return converter(numericValue);
  };

  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
  return mapObjIndexed((value) => convertValue(value), tokens) as {
    [K in keyof T]: number;
  };
};

export const convertRemTokensToNumberPixels = <T extends Record<string, `${number}rem`>>(
  remTokens: T
) => convertNumericTokensWithSuffix(remTokens, 'rem', (remValue) => remValue * BASE_REM_SIZE_PX);

export const convertPxTokensToNumberPixels = <T extends Record<string, `${number}px`>>(
  pxTokens: T
) => convertNumericTokensWithSuffix(pxTokens, 'px');

export const convertNumberTokensToStrings = <T extends Record<string, number>>(
  numberTokens: T
): { [K in keyof T]: T[K] extends number ? `${T[K]}` : string } =>
  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
  mapObjIndexed((value) => String(value), numberTokens) as {
    [K in keyof T]: T[K] extends number ? `${T[K]}` : string;
  };
