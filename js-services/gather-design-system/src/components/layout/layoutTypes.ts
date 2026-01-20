import { GatherDesignSystemColors, tokens } from '@gathertown/gather-design-foundations';

type ScaleTokenKeys = keyof typeof tokens.scale;
type ScaleTokenStringValues = (typeof tokens.scale)[ScaleTokenKeys];
type ScaleTokenValue = ScaleTokenKeys | ScaleTokenStringValues;

type NegativeScaleTokenKeys = keyof typeof tokens.negativeScale;
type NegativeScaleTokenStringValues = (typeof tokens.negativeScale)[NegativeScaleTokenKeys];
type NegativeScaleTokenValue = NegativeScaleTokenKeys | NegativeScaleTokenStringValues;

type SpacingUnit<TRestrictedSet extends string> =
  | `${TRestrictedSet}%`
  | `${TRestrictedSet}vh`
  | `${TRestrictedSet}vw`
  | `${TRestrictedSet}vmin`
  | `${TRestrictedSet}vmax`
  | `${TRestrictedSet}px`
  | '0';

export type SpacingTokenType = ScaleTokenValue | SpacingUnit<ScaleTokenStringValues>;
export type SpacingUnrestrictedType = number | SpacingUnit<string>;

type MarginTokenType = ScaleTokenValue | NegativeScaleTokenValue | 'auto';
type PositionTokenType = ScaleTokenValue | NegativeScaleTokenValue;

type RadiusTokenKeys = keyof typeof tokens.borderRadius;
type RadiusTokenStringValues = (typeof tokens.borderRadius)[RadiusTokenKeys];
type RadiusType = RadiusTokenKeys | RadiusTokenStringValues;

type ContentSizeType = 'auto' | 'min-content' | 'max-content' | 'fit-content';

export type LayoutStyleProps = {
  p: SpacingTokenType;
  px: SpacingTokenType;
  py: SpacingTokenType;
  pt: SpacingTokenType;
  pb: SpacingTokenType;
  pl: SpacingTokenType;
  pr: SpacingTokenType;

  m: MarginTokenType;
  mx: MarginTokenType;
  my: MarginTokenType;
  mt: MarginTokenType;
  mb: MarginTokenType;
  ml: MarginTokenType;
  mr: MarginTokenType;

  width: SpacingUnrestrictedType | ContentSizeType;
  height: SpacingUnrestrictedType | ContentSizeType;
  minWidth: SpacingUnrestrictedType | ContentSizeType;
  minHeight: SpacingUnrestrictedType | ContentSizeType;
  maxWidth: SpacingUnrestrictedType | ContentSizeType;
  maxHeight: SpacingUnrestrictedType | ContentSizeType;

  top: PositionTokenType;
  right: PositionTokenType;
  bottom: PositionTokenType;
  left: PositionTokenType;

  borderRadius: RadiusType;
  borderWidth: SpacingTokenType;

  gridArea: string;
  gridColumn: string;
  gridColumnStart: string;
  gridColumnEnd: string;
  gridRow: string;
  gridRowStart: string;
  gridRowEnd: string;

  opacity: number;
};

export type OverrideStyleProps = {
  style: React.CSSProperties;
};

// Note that additional properties such as `direction`, `justify, and `align` are added in
// `layoutSprinkles.css.ts` in the `shortenedLayoutSprinklesKeyMap`.
export type FlexParentStyleProps = {
  flex: number;
  gap: SpacingTokenType;
};

export type FlexChildStyleProps = {
  flexBasis: SpacingUnrestrictedType | 'auto';
  flexGrow: string | number;
  flexShrink: string | number;
};

export type AllFlexStyleProps = FlexParentStyleProps & FlexChildStyleProps;

export type GridStyleProps = {
  columns: string;
  rows: string;
  gap: SpacingTokenType;
  area: string;
  align: string;
  flow: string;
  rowsGap: SpacingTokenType;
};

export type ContainerStyleProps = {
  size: SpacingTokenType;
};

export type SectionStyleProps = {
  size: SpacingTokenType;
};

export type StyleProps = {
  backgroundColor: keyof GatherDesignSystemColors['bg'];
  borderColor: keyof GatherDesignSystemColors['border'];
  color: keyof GatherDesignSystemColors['text'];
  opacity: number;
  pointerEvents: 'all' | 'auto' | 'none';
};

export type AllPossibleProps = LayoutStyleProps &
  AllFlexStyleProps &
  ContainerStyleProps &
  StyleProps;

export enum PaddingStyles {
  p = 'padding',
  pt = 'paddingTop',
  pb = 'paddingBottom',
  pl = 'paddingLeft',
  pr = 'paddingRight',
}

export enum MarginStyles {
  m = 'margin',
  mt = 'marginTop',
  mb = 'marginBottom',
  ml = 'marginLeft',
  mr = 'marginRight',
}

export enum PositionStyles {
  top = 'top',
  right = 'right',
  bottom = 'bottom',
  left = 'left',
}

export enum DimensionStyles {
  width = 'width',
  height = 'height',
  minWidth = 'minWidth',
  minHeight = 'minHeight',
  maxWidth = 'maxWidth',
  maxHeight = 'maxHeight',
}

export enum FlexStyles {
  flexBasis = 'flexBasis',
  flexGrow = 'flexGrow',
  flexShrink = 'flexShrink',
  flex = 'flex',
}

export enum BorderStyles {
  borderColor = 'borderColor',
  borderWidth = 'borderWidth',
  borderRadius = 'borderRadius',
}

export enum BackgroundColorStyles {
  backgroundColor = 'backgroundColor',
}

export enum ColorStyles {
  color = 'color',
}

export enum OpacityStyles {
  opacity = 'opacity',
}

export enum FlexGapStyles {
  gap = 'gap',
}

export enum ContainerStyles {
  size = 'maxWidth',
}

export enum LayoutComponentTypes {
  box = 'box',
  section = 'section',
  flex = 'flex',
  container = 'container',
}

export enum PointerEventsStyles {
  pointerEvents = 'pointerEvents',
}

export type StyleEnum =
  | PaddingStyles
  | MarginStyles
  | PositionStyles
  | DimensionStyles
  | FlexStyles
  | BorderStyles
  | FlexGapStyles
  | BackgroundColorStyles
  | ColorStyles
  | OpacityStyles
  | ContainerStyles
  | LayoutComponentTypes
  | PointerEventsStyles;
