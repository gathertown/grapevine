import { invertObj } from 'ramda';

import { isArray, isString } from '../../utils/fpHelpers';
import { theme } from '@gathertown/gather-design-foundations';
import { shortenedLayoutSprinklesKeyMap } from './layoutSprinkles.css';
import {
  AllPossibleProps,
  BackgroundColorStyles,
  BorderStyles,
  ColorStyles,
  ContainerStyles,
  DimensionStyles,
  FlexGapStyles,
  FlexStyles,
  MarginStyles,
  OpacityStyles,
  PaddingStyles,
  PointerEventsStyles,
  PositionStyles,
  StyleEnum,
} from './layoutTypes';

// Anything property with an explicit number value should be converted to a string with a px value
export const baseStyleMap: Record<string, StyleEnum[] | StyleEnum> = {
  p: PaddingStyles.p,
  px: [PaddingStyles.pl, PaddingStyles.pr],
  py: [PaddingStyles.pt, PaddingStyles.pb],
  pt: PaddingStyles.pt,
  pb: PaddingStyles.pb,
  pl: PaddingStyles.pl,
  pr: PaddingStyles.pr,
  m: MarginStyles.m,
  mx: [MarginStyles.ml, MarginStyles.mr],
  my: [MarginStyles.mt, MarginStyles.mb],
  mt: MarginStyles.mt,
  mb: MarginStyles.mb,
  ml: MarginStyles.ml,
  mr: MarginStyles.mr,
  top: PositionStyles.top,
  right: PositionStyles.right,
  bottom: PositionStyles.bottom,
  left: PositionStyles.left,
  width: DimensionStyles.width,
  height: DimensionStyles.height,
  maxWidth: DimensionStyles.maxWidth,
  maxHeight: DimensionStyles.maxHeight,
  minWidth: DimensionStyles.minWidth,
  minHeight: DimensionStyles.minHeight,
  flexBasis: FlexStyles.flexBasis,
  flex: FlexStyles.flex,
  flexGrow: FlexStyles.flexGrow,
  flexShrink: FlexStyles.flexShrink,
  borderColor: BorderStyles.borderColor,
  borderWidth: BorderStyles.borderWidth,
  borderRadius: BorderStyles.borderRadius,
  gap: FlexGapStyles.gap,
  backgroundColor: BackgroundColorStyles.backgroundColor,
  color: ColorStyles.color,
  opacity: OpacityStyles.opacity,
  pointerEvents: PointerEventsStyles.pointerEvents,
};

export const containerStyleMap: Record<string, StyleEnum> = {
  ...baseStyleMap,
  size: ContainerStyles.size,
};

export const sectionStyleMap: Record<string, StyleEnum[] | StyleEnum> = {
  ...baseStyleMap,
  size: [PaddingStyles.pt, PaddingStyles.pb],
};

// These properties should be left as a number value
const useRawNumberValueMap: Record<string, boolean> = {
  [OpacityStyles.opacity]: true,
  [FlexStyles.flexGrow]: true,
  [FlexStyles.flexShrink]: true,
};

const themeColorMap = {
  [BackgroundColorStyles.backgroundColor]: theme.bg,
  [ColorStyles.color]: theme.text,
  [BorderStyles.borderColor]: theme.border,
} as const;

function isThemeColorKey(key: string): key is keyof typeof themeColorMap {
  return Object.hasOwn(themeColorMap, key);
}

export const translateStyleProps = (
  props: Partial<AllPossibleProps>,
  styleMap: Record<string, StyleEnum[] | StyleEnum>
) => {
  const convertValue = (styleKey: string, value: string | number) => {
    if (useRawNumberValueMap[styleKey]) return value;

    if (isThemeColorKey(styleKey))
      // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
      return themeColorMap[styleKey][value as keyof (typeof themeColorMap)[typeof styleKey]];

    return isString(value) ? value : `${value}px`;
  };

  return Object.entries(props).reduce<React.CSSProperties>((styleProps, [key, value]) => {
    const styleMapping = styleMap[key];
    if (!styleMapping) return styleProps;

    if (isArray(styleMapping)) {
      return {
        ...styleMapping.reduce(
          (acc, styleKey) => ({
            ...acc,
            [styleKey]: convertValue(styleKey, value),
          }),
          {}
        ),
        ...styleProps,
      };
    }

    return {
      [styleMapping]: convertValue(styleMapping, value),
      ...styleProps,
    };
  }, {});
};

const shortenedKeyToBaseKeyMap = invertObj(shortenedLayoutSprinklesKeyMap);

const getRemappedKeyOrDefault = (key: string) => {
  const possiblyRemappedKey = shortenedKeyToBaseKeyMap[key];
  return possiblyRemappedKey ?? key;
};

export const getSprinkleStyle = <T, R>(
  props: Partial<T>,
  styleMap: Record<string, StyleEnum[] | StyleEnum>
) =>
  Object.entries(props).reduce<R>(
    (acc, [key, value]) => {
      if (styleMap[key]) return acc;

      return {
        [getRemappedKeyOrDefault(key)]: value,
        ...acc,
      };
    },
    // Intentionally cast into R
    // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
    {} as R
  );
