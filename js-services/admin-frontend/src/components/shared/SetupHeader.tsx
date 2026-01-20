import type { FC, ReactNode } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';
import grapevineLogoUrl from '../../assets/grapevine_purp.png';

interface SetupHeaderProps {
  title: string;
  primaryIcon?: ReactNode;
  showGrapevine?: boolean;
  showConnection?: boolean;
}

export const SetupHeader: FC<SetupHeaderProps> = ({
  title,
  primaryIcon,
  showGrapevine = false,
  showConnection = false,
}) => {
  return (
    <Flex direction="column" gap={16} align="center">
      {/* Icons Row */}
      {(primaryIcon || showGrapevine) && (
        <Flex style={{ alignItems: 'center' }} gap={16} justify="center">
          {primaryIcon && (
            <Flex style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}>
              {primaryIcon}
            </Flex>
          )}
          {showConnection && primaryIcon && showGrapevine && <Text fontSize="lg">⟷</Text>}
          {showGrapevine && <img src={grapevineLogoUrl} alt="Grapevine" width={48} height={48} />}
        </Flex>
      )}

      {/* Title */}
      <div style={{ textAlign: 'center' }}>
        <Text fontSize="lg" fontWeight="semibold">
          {title}
        </Text>
      </div>
    </Flex>
  );
};
