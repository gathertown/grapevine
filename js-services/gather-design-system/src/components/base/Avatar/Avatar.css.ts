import { CSSProperties, style, styleVariants } from '@vanilla-extract/css';
import { recipe, RecipeVariants } from '@vanilla-extract/recipes';

import { objectFromEntries, objectKeys, objectValues } from '../../../utils/tsUtils';
import { theme, tokens } from '@gathertown/gather-design-foundations';
import { CircleConfig, generateClipPathWithMultiCircleCutout } from '../../../helpers/clipPaths';
import { StatusIndicatorKind, statusIndicatorSizeMap } from '../Status/StatusIndicator';

export const avatarSizeMap = {
  xxxxs: 14,
  xxxs: 16,
  xxs: 20,
  xs: 24,
  sm: 32,
  md: 36,
  lg: 40,
  xl: 48,
  xxl: 88,
} as const;

export const avatarStatusDotSizeMap = {
  xxxxs: {
    statusSize: 'xs',
    borderWidth: 0,
  },
  xxxs: {
    statusSize: 'xs',
    borderWidth: 1.5,
  },
  xxs: {
    statusSize: 'xs',
    borderWidth: 1.5,
  },
  xs: {
    statusSize: 'sm',
    borderWidth: 2,
  },
  sm: {
    statusSize: 'md',
    borderWidth: 2,
  },
  md: {
    statusSize: 'md',
    borderWidth: 2,
  },
  lg: {
    statusSize: 'lg',
    borderWidth: 3,
  },
  xl: {
    statusSize: 'lg',
    borderWidth: 3,
  },
  xxl: {
    statusSize: 'lg',
    borderWidth: 3,
  },
} as const;

export const avatarRecipe = recipe({
  base: {
    position: 'relative',
    userSelect: 'none',
    flexShrink: 0,
  },

  variants: {
    size: styleVariants(avatarSizeMap, (size) => ({
      height: size,
      width: size,
    })),
    fluid: {
      true: {
        width: '100%',
        height: '100%',
      },
    },
  },
});

export const avatarImageStyle = style({
  aspectRatio: '1 / 1',
  display: 'block',
  objectFit: 'cover',
  width: '100%',
});

const avatarBorderWidth = 0.5;
const avatarBorderColor = 'black';
const avatarBorderOpacity = 0.05;

export const avatarBorderRecipe = recipe({
  base: {
    border: `${avatarBorderWidth}px solid ${avatarBorderColor}`,
    clipPath: 'inherit',
    inset: 0,
    opacity: avatarBorderOpacity,
    overflow: 'hidden',
    position: 'absolute',
  },
  variants: {
    size: styleVariants(avatarStatusDotSizeMap, ({ statusSize, borderWidth }) => ({
      selectors: {
        [`&:after`]: {
          border: `${avatarBorderWidth}px solid ${avatarBorderColor}`,
          borderRadius: tokens.borderRadius.full,
          bottom: `${-(borderWidth + avatarBorderWidth * 2)}px`,
          content: '',
          height: `${statusIndicatorSizeMap[statusSize] + borderWidth * 2}px`,
          position: 'absolute',
          right: `${-(borderWidth + avatarBorderWidth * 2)}px`,
          width: `${statusIndicatorSizeMap[statusSize] + borderWidth * 2}px`,
        },
      },
    })),
  },
});

// Clip path is only applied if status is provided
// There are responsive ways of accomplishing this, but they are less performant than raw clip-paths
export const avatarClipPathStyles = styleVariants(avatarSizeMap, (size, sizeKey) => {
  const { statusSize, borderWidth } = avatarStatusDotSizeMap[sizeKey];
  const statusDiameter = statusIndicatorSizeMap[statusSize];
  const clipPathCircleDiameter = statusDiameter + borderWidth * 2;

  return {
    clipPath: generateClipPathWithMultiCircleCutout([
      {
        cx: size - statusDiameter / 2,
        cy: 0 + statusDiameter / 2,
        diameter: clipPathCircleDiameter,
        borderRadius: 6,
      },
      {
        cx: size - statusDiameter / 2,
        cy: size - statusDiameter / 2,
        diameter: clipPathCircleDiameter,
      },
    ]),
  };
});

const combine =
  (
    generateClipPath: typeof generateClipPathWithMultiCircleCutout,
    getCircles: (args: {
      statusDiameter: number;
      size: number;
      clipPathCircleDiameter: number;
    }) => CircleConfig[]
  ) =>
  (sizeKey: keyof typeof avatarSizeMap) => {
    const { statusSize, borderWidth } = avatarStatusDotSizeMap[sizeKey];
    const statusDiameter = statusIndicatorSizeMap[statusSize];
    const clipPathCircleDiameter = statusDiameter + borderWidth * 2;

    const size = avatarSizeMap[sizeKey];

    return generateClipPath(
      getCircles({
        clipPathCircleDiameter,
        statusDiameter,
        size,
      })
    );
  };

const generateWithBoth = combine(
  generateClipPathWithMultiCircleCutout,
  ({ statusDiameter, size, clipPathCircleDiameter }) => [
    {
      cx: size - statusDiameter / 2,
      cy: 0 + statusDiameter / 2,
      diameter: clipPathCircleDiameter,
      borderRadius: 6,
    },
    {
      cx: size - statusDiameter / 2,
      cy: size - statusDiameter / 2,
      diameter: clipPathCircleDiameter,
    },
  ]
);

const generateWithiconOnly = combine(
  generateClipPathWithMultiCircleCutout,
  ({ statusDiameter, size, clipPathCircleDiameter }) => [
    {
      cx: size - statusDiameter / 2,
      cy: 0 + statusDiameter / 2,
      diameter: clipPathCircleDiameter,
      borderRadius: 6,
    },
  ]
);

const generateWithStatusOnly = combine(
  generateClipPathWithMultiCircleCutout,
  ({ statusDiameter, size, clipPathCircleDiameter }) => [
    {
      cx: size - statusDiameter / 2,
      cy: size - statusDiameter / 2,
      diameter: clipPathCircleDiameter,
    },
  ]
);

type ClipPathMap = {
  variants: {
    app: true | false;
    status?: (typeof allStatusValues)[number];
    size: keyof typeof avatarSizeMap;
  };
  style: CSSProperties;
};

type OutlineMap = {
  variants: {
    status?: (typeof allStatusValues)[number];
    size: keyof typeof avatarSizeMap;
    showStatusOutline: true | false;
  };
  style: CSSProperties;
};

const outlineSizes: {
  [k in keyof typeof avatarSizeMap]: {
    padding: keyof typeof tokens.scale;
    borderWidth: keyof typeof tokens.scale;
  };
} = {
  xxxxs: { padding: 0, borderWidth: 0 },
  xxxs: { padding: 0, borderWidth: 0 },
  xxs: { padding: 1, borderWidth: 2 },
  xs: { padding: 1, borderWidth: 2 },
  sm: { padding: 2, borderWidth: 2 },
  md: { padding: 2, borderWidth: 2 },
  lg: { padding: 2, borderWidth: 2 },
  xl: { padding: 2, borderWidth: 2 },
  xxl: { padding: 2, borderWidth: 2 },
};

const themeMap: Partial<Record<StatusIndicatorKind | 'custom', keyof typeof theme.presence>> = {
  [StatusIndicatorKind.Active]: 'online',
  [StatusIndicatorKind.Busy]: 'busy',
  [StatusIndicatorKind.Away]: 'away',
  [StatusIndicatorKind.Offline]: 'offline',
  // TODO: if the rendered component does not pass in a static status, but instead a custom rendering
  // we won't know which color to use, we default to online currently for "extremely active" use case
  custom: 'online',
};

const statusValues = objectValues(StatusIndicatorKind);
const allStatusValues = [...statusValues, 'custom' as const];
const sizeValues = objectKeys(avatarSizeMap);

export const avatarClipPathRecipe = recipe({
  variants: {
    app: { true: {}, false: {} },
    showStatusOutline: { true: {}, false: {} },
    status: {
      ...objectFromEntries(allStatusValues.map((kind) => [kind, {}] as const)),
    },
    size: {
      ...objectFromEntries(sizeValues.map((key) => [key, {}] as const)),
    },
  },

  compoundVariants: [
    ...sizeValues
      .map((sizeKey) =>
        allStatusValues.map(
          (colorKey): OutlineMap => ({
            variants: { status: colorKey, size: sizeKey, showStatusOutline: true },
            style: themeMap[colorKey]
              ? {
                  borderRadius: '100%',
                  padding: tokens.scale[outlineSizes[sizeKey].padding],
                  border: `${tokens.scale[outlineSizes[sizeKey].borderWidth]} solid ${
                    theme.presence[themeMap[colorKey]]
                  }`,
                }
              : {},
          })
        )
      )
      .flat(),

    ...sizeValues
      .map((sizeKey) =>
        allStatusValues.map(
          (status): ClipPathMap => ({
            variants: { app: true, status, size: sizeKey },
            style: {
              clipPath: generateWithBoth(sizeKey),
            },
          })
        )
      )
      .flat(),
    ...sizeValues
      .map((sizeKey) =>
        allStatusValues.map(
          (status): ClipPathMap => ({
            variants: { app: false, status, size: sizeKey },
            style: {
              clipPath: generateWithStatusOnly(sizeKey),
            },
          })
        )
      )
      .flat(),
    ...sizeValues.map(
      (sizeKey): ClipPathMap => ({
        variants: { app: true, status: undefined, size: sizeKey },
        style: {
          clipPath: generateWithiconOnly(sizeKey),
        },
      })
    ),
  ],
});

export const borderRadiusStyles = styleVariants({
  circle: {
    borderRadius: tokens.borderRadius.full,
  },
  square: {
    borderRadius: tokens.borderRadius[14],
  },
});

export type AvatarVariants = RecipeVariants<typeof avatarRecipe>;
