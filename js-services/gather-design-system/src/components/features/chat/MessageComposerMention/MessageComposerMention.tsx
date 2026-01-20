import React, { useEffect, useImperativeHandle, useState } from 'react';

import { Text } from '../../../base/Text/Text';
import { Flex } from '../../../layout/Flex/Flex';
import { Scrollable } from '../../../layout/Scrollable/Scrollable';
import type { BaseQueryItem } from './generateMentionConfig';
import { dropdownContainerStyle, dropdownItemRecipe } from './MessageComposerMention.css';

type MessageComposerMentionProps = {
  items: BaseQueryItem[];
  command: (item: BaseQueryItem) => void;
  ref: React.Ref<{ onKeyDown: ({ event }: { event: KeyboardEvent }) => boolean }>;
};

export function MessageComposerMention(props: MessageComposerMentionProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const selectedItemRef = React.useRef<HTMLButtonElement | null>(null);

  const selectItem = (index: number) => {
    const item = props.items[index];

    if (item) {
      props.command(item);
    }
  };

  const onKeyPressUp = () => {
    setSelectedIndex((selectedIndex + props.items.length - 1) % props.items.length);
  };

  const onKeyPressDown = () => {
    setSelectedIndex((selectedIndex + 1) % props.items.length);
  };

  const onKeyPressEnterOrTab = () => {
    selectItem(selectedIndex);
  };

  const handleItemMouseEnter = (index: number) => () => {
    setSelectedIndex(index);
  };

  useEffect(() => setSelectedIndex(0), [props.items]);

  useEffect(() => {
    if (containerRef.current && selectedItemRef.current) {
      // Only scroll into view if the selected item is not in the viewport
      const selectedItemRect = selectedItemRef.current.getBoundingClientRect();
      const containerRect = containerRef.current.getBoundingClientRect();
      const isInView =
        selectedItemRect.top >= containerRect.top &&
        selectedItemRect.bottom <= containerRect.bottom;

      if (!isInView) {
        selectedItemRef.current.scrollIntoView();
      }
    }
  }, [selectedIndex]);

  const hasPotentialMatch = props.items.length > 0;

  useImperativeHandle(props.ref, () => ({
    onKeyDown: ({ event }: { event: KeyboardEvent }) => {
      if (event.key === 'ArrowUp') {
        onKeyPressUp();
        return true;
      }

      if (event.key === 'ArrowDown') {
        onKeyPressDown();
        return true;
      }

      if ((event.key === 'Enter' || event.key === 'Tab') && hasPotentialMatch) {
        onKeyPressEnterOrTab();
        return true;
      }

      return false;
    },
  }));

  // Hide the dropdown if there are no items.
  if (!hasPotentialMatch) return null;

  return (
    <div className={dropdownContainerStyle} ref={containerRef}>
      <Scrollable
        style={{ display: 'flex', flexDirection: 'column' }}
        flexGrow={1}
        flexShrink={1}
        scrollDirection="y"
      >
        <Flex direction="column" gap={2} p={4}>
          {props.items.map((item, index) => (
            <button
              className={dropdownItemRecipe({ isSelected: index === selectedIndex })}
              ref={index === selectedIndex ? selectedItemRef : null}
              key={index}
              onClick={() => selectItem(index)}
              onMouseEnter={handleItemMouseEnter(index)}
            >
              <Text truncate>{item.label}</Text>
            </button>
          ))}
        </Flex>
      </Scrollable>
    </div>
  );
}
