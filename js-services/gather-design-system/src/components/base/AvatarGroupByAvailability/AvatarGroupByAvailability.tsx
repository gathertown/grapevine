import React, { useMemo } from 'react';

import { tokens } from '@gathertown/gather-design-foundations';
import { AvatarItem } from '../../../helpers/avatars';
import { Flex } from '../../layout/Flex/Flex';
import { Avatar, AvatarProps } from '../Avatar/Avatar';
import { avatarSizeMap } from '../Avatar/Avatar.css';
import { StatusIndicator, StatusIndicatorKind } from '../Status/StatusIndicator';
import { Text } from '../Text/Text';
import { cascadeContainerStyles } from './AvatarGroupByAvailability.css';

type Props = {
  size: AvatarProps['size'];
  avatars: AvatarItem[];
  targetStatus?: StatusIndicatorKind;
};

// Shows first three members and displays the full count of users matching target status in a pill
// This copied a lot of code from AvatarGroup. The components are different enough where merging APIs would be a bit awkward
export const AvatarGroupByAvailability = React.memo(function AvatarGroupByAvailability({
  size = 'md',
  avatars,
  targetStatus = StatusIndicatorKind.Active,
}: Props) {
  const matchingUsers = useMemo(
    () => avatars.filter((avatar) => avatar.status === targetStatus),
    [avatars, targetStatus]
  );

  const avatarsToRender = useMemo(() => matchingUsers.slice(0, 3), [matchingUsers]);

  return (
    <Flex justify="center" align="center">
      {avatarsToRender.map(({ key, ...avatar }) => (
        <div key={key} className={cascadeContainerStyles[size]}>
          <Avatar {...avatar} size={size} status={undefined} />
        </div>
      ))}
      <div className={cascadeContainerStyles[size]}>
        <Flex
          borderWidth={1}
          borderColor="quaternary"
          borderStyle="solid"
          borderRadius={tokens.borderRadius.full}
          align="center"
          justify="center"
          flexShrink={0}
          gap={2}
          px={6}
          py={4}
          backgroundColor="secondary"
          height={avatarSizeMap[size]}
          minWidth={avatarSizeMap[size] * 1.25}
          style={{
            boxSizing: 'border-box',
          }}
        >
          <Text color="tertiary" fontWeight="medium" fontSize="xxs">
            {matchingUsers.length}
          </Text>
          <StatusIndicator size="xs" kind={targetStatus} />
        </Flex>
      </div>
    </Flex>
  );
});
