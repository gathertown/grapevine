import { styleVariants } from '@vanilla-extract/css';

import { generateInvertedCircleClipPath } from '../../../helpers/clipPaths';
import { avatarSizeMap } from '../Avatar/Avatar.css';

export const cascadeContainerStyles = styleVariants(avatarSizeMap, (size) => ({
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
