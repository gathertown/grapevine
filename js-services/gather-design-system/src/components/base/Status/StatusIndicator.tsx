import React from 'react';

import { theme, tokens } from '@gathertown/gather-design-foundations';
import { Flex } from '../../layout/Flex/Flex';
import {
  EventAccepted,
  EventDeclined,
  EventMaybe,
  StatusActive,
  StatusAway,
  StatusBusy,
  StatusOffline,
} from './generated';

export const statusIndicatorSizeMap = {
  xs: 6,
  sm: 8,
  md: 10,
  lg: 12,
} as const;

export enum StatusIndicatorKind {
  Active = 'active',
  Busy = 'busy',
  Away = 'away',
  Offline = 'offline',
  Accepted = 'accepted',
  Declined = 'declined',
  NeedsAction = 'needsAction',
  Tentative = 'tentative',
  FocusedCoworking = 'focusedCoworking',
}

export type StatusIndicatorProps = {
  kind?: StatusIndicatorKind;
  size?: keyof typeof statusIndicatorSizeMap;
};

const { presence, eventStatus, bg } = theme;

const iconMap: Record<StatusIndicatorKind, React.ReactElement> = {
  [StatusIndicatorKind.Active]: <StatusActive style={{ color: presence.online }} />,
  [StatusIndicatorKind.FocusedCoworking]: <StatusActive style={{ color: bg.accentPrimary }} />,
  [StatusIndicatorKind.Busy]: <StatusBusy style={{ color: presence.busy }} />,
  [StatusIndicatorKind.Away]: <StatusAway style={{ color: presence.away }} />,
  [StatusIndicatorKind.Offline]: <StatusOffline style={{ color: presence.offline }} />,
  [StatusIndicatorKind.Accepted]: <EventAccepted style={{ color: eventStatus.accepted }} />,
  [StatusIndicatorKind.Declined]: <EventDeclined style={{ color: eventStatus.declined }} />,
  [StatusIndicatorKind.NeedsAction]: <EventMaybe style={{ color: eventStatus.needsAction }} />,
  [StatusIndicatorKind.Tentative]: <EventMaybe style={{ color: eventStatus.tentative }} />,
};

export const StatusIndicator = React.memo(function StatusIndicator({
  size = 'sm',
  kind = StatusIndicatorKind.Active,
}: StatusIndicatorProps) {
  const statusSize = statusIndicatorSizeMap[size];

  return (
    <Flex
      borderRadius={tokens.borderRadius.full}
      width={statusSize}
      height={statusSize}
      flexShrink={0}
      justify="center"
      align="center"
    >
      {iconMap[kind]}
    </Flex>
  );
});
