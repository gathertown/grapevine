import { styleVariants } from '@vanilla-extract/css';

import { theme, tokens } from '@gathertown/gather-design-foundations';
import { generateInvertedCircleClipPath } from '../../../helpers/clipPaths';
import { avatarSizeMap } from '../Avatar/Avatar.css';

export const avatarContainerStyles = styleVariants(avatarSizeMap, (size) => ({
  selectors: {
    '&:not(:first-of-type)': {
      marginLeft: -(size / 4),
    },
    '&:not(:last-of-type)': {
      clipPath: generateInvertedCircleClipPath(
        size + size / 4,
        size / 2,
        size + Math.floor(size / 10) * 2
      ),
    },
  },
}));

export const additionalAvatarContainerStyles = styleVariants(avatarSizeMap, (size) => ({
  height: size,
  minWidth: size,
  paddingLeft: size <= 20 ? 4 : 6, // Smaller padding for xxxs and smaller
  paddingRight: size <= 20 ? 4 : 6,
  backgroundColor: theme.bg.secondary,
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  borderRadius: tokens.borderRadius.full,
  border: `0.5px solid ${theme.border.quaternary}`,
  overflow: 'hidden',
}));
