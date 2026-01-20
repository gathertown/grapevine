import React, { memo, useMemo } from 'react';

import { Button } from '../../../base/Button/Button';
import { IconProps } from '../../../base/Icon/Icon';
import { IconButton } from '../../../base/IconButton/IconButton';
import { Flex } from '../../../layout/Flex/Flex';
import { dividerStyle } from './MessageComposerActionsToolbar.css';
import { ResponsiveActionsGroup } from './ResponsiveActionsGroup';

export type ComposerAction =
  | {
      type: 'action';
      icon: IconProps['name'];
      name: string;
      isActive?: boolean;
      isPrimary?: boolean;
      isContrast?: boolean;
      isDisabled?: boolean;
      onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
    }
  | {
      type: 'buttonAction';
      name: string;
      isPrimary?: boolean;
      onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
      isDisabled?: boolean;
    }
  | {
      type: 'component';
      render: () => React.ReactNode;
    }
  | {
      type: 'divider';
    };

type MessageComposerActionsToolbarProps = {
  composerActionsStart: ComposerAction[];
  composerActionsEnd?: ComposerAction[];
  useResponsiveFormatting?: boolean;
  isInline?: boolean;
};

export const MessageComposerActionsToolbar: React.FC<MessageComposerActionsToolbarProps> = memo(
  function MessageComposerActionsToolbar({
    composerActionsStart,
    composerActionsEnd = [],
    useResponsiveFormatting = false,
    isInline = false,
  }) {
    const { basicActions, formattingActions } = useMemo(() => {
      const dividerIndex = composerActionsStart.findIndex((action) => action.type === 'divider');

      if (!useResponsiveFormatting || dividerIndex === -1)
        return { basicActions: composerActionsStart, formattingActions: [] };

      const basic = composerActionsStart.slice(0, dividerIndex);
      const formatting = composerActionsStart
        .slice(dividerIndex + 1)
        .filter((action) => action.type === 'action');

      return { basicActions: basic, formattingActions: formatting };
    }, [composerActionsStart, useResponsiveFormatting]);

    const renderAction = (action: ComposerAction, index: number) => {
      switch (action.type) {
        case 'action':
          return (
            <IconButton
              key={action.icon}
              icon={action.icon}
              size="md"
              kind={action.isPrimary ? 'primary' : action.isActive ? 'secondary' : 'transparent'}
              onClick={action.onClick}
              tooltip={action.isDisabled ? undefined : action.name}
              disabled={action.isDisabled}
              data-testid={`gather-chat-composer-${action.name}-button`}
            />
          );

        case 'buttonAction':
          return (
            <Button
              key={action.name}
              size="md"
              kind={action.isPrimary ? 'primary' : 'secondary'}
              onClick={action.onClick}
              disabled={action.isDisabled}
              data-testid={`gather-chat-composer-${action.name}-button`}
            >
              {action.name}
            </Button>
          );

        case 'component':
          return <div key={`component_${index}`}>{action.render()}</div>;

        case 'divider':
          return <div key={`divider_${index}`} className={dividerStyle} />;
      }
    };

    if (useResponsiveFormatting && formattingActions.length > 0) {
      return (
        <Flex gap={4} flexGrow={1} justify="space-between">
          <Flex gap={4} flexGrow={1}>
            {basicActions.map((action, index) => renderAction(action, index))}
            {formattingActions.length > 0 && <div className={dividerStyle} />}
            <ResponsiveActionsGroup actions={formattingActions} priorityCount={3} />
          </Flex>
          <Flex gap={4}>
            {composerActionsEnd.map((action, index) => renderAction(action, index))}
          </Flex>
        </Flex>
      );
    }

    return (
      <Flex gap={isInline ? 0 : 4} flexGrow={isInline ? undefined : 1} justify="space-between">
        {([composerActionsStart, composerActionsEnd] as const).map((actions, groupIndex) => (
          <Flex key={groupIndex} gap={4}>
            {actions.map((action, index) => renderAction(action, index))}
          </Flex>
        ))}
      </Flex>
    );
  }
);
