import React, { memo, useCallback, useEffect, useRef, useState } from 'react';

import { IconButton } from '../../../base/IconButton/IconButton';
import { Menu } from '../../../base/Menu/Menu';
import { Flex } from '../../../layout/Flex/Flex';
import { ComposerAction } from './MessageComposerActionsToolbar';

type ResponsiveActionsGroupProps = {
  actions: ComposerAction[];
  priorityCount?: number;
};

export const ResponsiveActionsGroup: React.FC<ResponsiveActionsGroupProps> = memo(
  function ResponsiveActionsGroup({ actions, priorityCount = 3 }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [visibleCount, setVisibleCount] = useState(actions.length);
    const [isMenuOpen, setIsMenuOpen] = useState(false);

    const checkOverflow = useCallback(() => {
      if (!containerRef.current) return;

      const container = containerRef.current;
      const containerWidth = container.offsetWidth;
      const buttonWidth = 32;
      const gap = 4;
      const moreButtonWidth = 32;

      const availableWidth = containerWidth - moreButtonWidth - gap;
      const maxVisibleButtons = Math.floor(availableWidth / (buttonWidth + gap));

      const newVisibleCount = Math.min(maxVisibleButtons, actions.length);
      setVisibleCount(Math.max(priorityCount, newVisibleCount));
    }, [actions.length, priorityCount]);

    useEffect(() => {
      checkOverflow();
      const resizeObserver = new ResizeObserver(checkOverflow);
      if (containerRef.current) {
        resizeObserver.observe(containerRef.current);
      }
      return () => resizeObserver.disconnect();
    }, [checkOverflow]);

    const visibleActions = actions.slice(0, visibleCount);
    const overflowActions = actions.slice(visibleCount);
    const hasOverflow = overflowActions.length > 0;

    const renderAction = (action: ComposerAction, index: number) => {
      switch (action.type) {
        case 'action':
          return (
            <IconButton
              key={`${action.icon}_${index}`}
              icon={action.icon}
              size="md"
              kind={action.isPrimary ? 'primary' : action.isActive ? 'secondary' : 'transparent'}
              onClick={action.onClick}
              tooltip={action.name}
              disabled={action.isDisabled}
              data-testid={`gather-chat-composer-${action.name}-button`}
            />
          );
        case 'divider':
          return null;
        default:
          return null;
      }
    };

    return (
      <Flex ref={containerRef} gap={4} flexGrow={1}>
        {visibleActions.map((action, index) => renderAction(action, index))}
        {hasOverflow && (
          <Menu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
            <Menu.Trigger>
              <IconButton
                icon="ellipsesH"
                size="md"
                kind="transparent"
                onClick={() => setIsMenuOpen(true)}
                tooltip="More formatting options"
                data-testid="gather-chat-composer-more-button"
              />
            </Menu.Trigger>
            <Menu.Content>
              {overflowActions.map((action, index) => {
                if (action.type === 'action') {
                  return (
                    <Menu.Item
                      key={`${action.icon}_overflow_${index}`}
                      icon={action.icon}
                      onSelect={() => {
                        // The onClick handlers in formatting actions don't use the event parameter
                        // so we can safely pass a dummy event
                        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
                        action.onClick({} as React.MouseEvent<HTMLButtonElement>);
                      }}
                      disabled={action.isDisabled}
                    >
                      {action.name}
                    </Menu.Item>
                  );
                }
                return null;
              })}
            </Menu.Content>
          </Menu>
        )}
      </Flex>
    );
  }
);
