import { createSprinkles, defineProperties } from '@vanilla-extract/sprinkles';

const layoutStyles = defineProperties({
  properties: {
    position: ['static', 'relative', 'absolute', 'fixed', 'sticky'],
    borderStyle: ['solid', 'dashed', 'dotted', 'double', 'none'],
    overflow: ['visible', 'hidden', 'scroll', 'auto'],
    overflowX: ['visible', 'hidden', 'scroll', 'auto'],
    overflowY: ['visible', 'hidden', 'scroll', 'auto'],
  },
  shorthands: {},
});

const flexStyles = defineProperties({
  properties: {
    display: ['flex', 'inline-flex', 'none'],
    flexDirection: ['row', 'row-reverse', 'column', 'column-reverse'],
    alignItems: ['stretch', 'flex-start', 'flex-end', 'center', 'baseline'],
    justifyContent: ['flex-start', 'flex-end', 'center', 'space-between', 'space-around'],
    flexWrap: ['nowrap', 'wrap', 'wrap-reverse'],
  },
});

const containerStyles = defineProperties({
  properties: {
    display: ['initial', 'none'],
    align: ['left', 'center', 'right'],
  },
});

export const shortenedLayoutSprinklesKeyMap = {
  flexDirection: 'direction',
  alignItems: 'align',
  justifyContent: 'justify',
} as const satisfies Partial<{
  [key in AllBaseKeys]: string;
}>;

// Create sprinkles for layout only
export const layoutSprinkles = createSprinkles(layoutStyles);

// Create sprinkles for layout and flex combined
export const flexSprinkles = createSprinkles(layoutStyles, flexStyles);

// Create sprinkles for container
export const containerSprinkles = createSprinkles(containerStyles, layoutStyles, flexStyles);

// Type helpers for remapping keys for shortening
type KeyMap = {
  [key: string]: string;
};
export type ShortenedLayoutSprinklesKeyMap = typeof shortenedLayoutSprinklesKeyMap;
type RenameKeys<T, U extends KeyMap> = {
  [K in keyof T as K extends keyof U ? (U[K] extends string ? U[K] : never) : K]: K extends keyof T
    ? T[K]
    : never;
};

// Original ("base") types before remap
type LayoutSprinklesBase = Parameters<typeof layoutSprinkles>[0];
type FlexSprinklesBase = Parameters<typeof flexSprinkles>[0];
type ContainerSprinklesBase = Parameters<typeof containerSprinkles>[0];

type AllBaseKeys = keyof (LayoutSprinklesBase & FlexSprinklesBase & ContainerSprinklesBase);

// Remapped types
export type LayoutSprinkles = RenameKeys<LayoutSprinklesBase, ShortenedLayoutSprinklesKeyMap>;
export type FlexSprinkles = RenameKeys<FlexSprinklesBase, ShortenedLayoutSprinklesKeyMap>;
export type ContainerSprinkles = RenameKeys<ContainerSprinklesBase, ShortenedLayoutSprinklesKeyMap>;
