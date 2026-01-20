import React from 'react';

import { isNotNilAndNotEmpty } from '../../../utils/fpHelpers';
import { theme, tokens } from '@gathertown/gather-design-foundations';
import { AvatarItem } from '../../../helpers/avatars';
import { cx } from '../../../helpers/classnames';
import { Flex } from '../../layout/Flex/Flex';
import { Avatar, AvatarProps } from '../Avatar/Avatar';
import { avatarSizeMap } from '../Avatar/Avatar.css';
import { Tooltip } from '../Tooltip/Tooltip';
import { additionalAvatarContainerStyles, avatarContainerStyles } from './AvatarGroup.css';

export type AvatarGroupProps = {
  size: AvatarProps['size'];
  avatars: AvatarItem[];
  maxShownAvatars?: number;
  showAdditionalAvatarsTooltip?: boolean;
  showAvatarTooltip?: boolean;
};

const getAvatarOverflow = (avatars: AvatarItem[], maxShownAvatars: number) => {
  if (avatars.length <= maxShownAvatars) return { avatarsToRender: avatars, additionalAvatars: [] };

  return {
    avatarsToRender: avatars.slice(0, maxShownAvatars - 1),
    additionalAvatars: avatars.slice(maxShownAvatars - 1),
  };
};

export const AvatarGroup = React.memo(
  React.forwardRef<HTMLDivElement, AvatarGroupProps>(function AvatarGroup(
    {
      avatars,
      size = 'md',
      maxShownAvatars = 3,
      showAdditionalAvatarsTooltip = true,
      showAvatarTooltip = false,
    },
    ref
  ) {
    const { avatarsToRender, additionalAvatars } = getAvatarOverflow(avatars, maxShownAvatars);

    let additionalAvatarsContent: React.ReactNode = null;
    if (additionalAvatars.length > 0) {
      // Calculate fontSize based on avatar size for better readability
      // Smaller avatars need proportionally larger text to be readable
      const avatarSize = avatarSizeMap[size];
      const fontSize = avatarSize <= 16 ? 16 : avatarSize <= 24 ? 15 : 14;

      additionalAvatarsContent = (
        <div className={cx(avatarContainerStyles[size], additionalAvatarContainerStyles[size])}>
          <svg
            viewBox="0 0 24 24"
            style={{
              height: '100%',
              aspectRatio: '1 / 1',
              display: 'block',
            }}
          >
            <text
              x="50%"
              y="50%"
              textAnchor="middle"
              dominantBaseline="central"
              fill={theme.text.secondary}
              fontWeight={tokens.fontWeight.semibold}
              fontSize={fontSize}
            >
              {`+${additionalAvatars.length}`}
            </text>
          </svg>
        </div>
      );

      if (showAdditionalAvatarsTooltip) {
        const tooltip = additionalAvatars
          .map(({ name }) => name)
          .filter(isNotNilAndNotEmpty)
          // TODO: this is no good for i18n
          .join(', ');

        additionalAvatarsContent = <Tooltip content={tooltip}>{additionalAvatarsContent}</Tooltip>;
      }
    }

    return (
      <Flex ref={ref}>
        {avatarsToRender.map(({ key, ...avatar }) => (
          <div key={key} className={avatarContainerStyles[size]}>
            <Avatar size={size} tooltip={showAvatarTooltip ? avatar.name : undefined} {...avatar} />
          </div>
        ))}
        {additionalAvatarsContent}
      </Flex>
    );
  })
);
