import * as Tabs from '@radix-ui/react-tabs';
import React from 'react';

import { Box } from '../../layout/Box/Box';
import { Flex } from '../../layout/Flex/Flex';
import { Icon, IconName } from '../Icon/Icon';
import { Text } from '../Text/Text';
import {
  tabsContentStyle,
  tabsIconImageContainerStyles,
  tabsIconImageStyle,
  tabsListStyle,
  tabsRootStyle,
  tabsTriggerStyle,
} from './ModalTabs.css';

export type ModalTabConfig =
  | {
      kind: 'icon';
      icon: IconName;
      value: string;
      label: string;
      renderContent: (props: { label: string }) => React.ReactNode;
      isHidden?: boolean;
      isHiddenCallback?: () => boolean;
      dataTestId?: string;
    }
  | {
      kind: 'image';
      src: string;
      value: string;
      label: string;
      renderContent: (props: { label: string }) => React.ReactNode;
      isHidden?: boolean;
      isHiddenCallback?: () => boolean;
      dataTestId?: string;
    };

export type ModalTabsProps = {
  defaultValue?: string;
  headerContent?: React.ReactNode;
  onValueChange?: (value: string) => void;
  tabGroups: {
    title?: string;
    tabs: ModalTabConfig[];
  }[];
  value?: string;
};

export function ModalTabs({
  defaultValue,
  headerContent,
  onValueChange,
  tabGroups,
  value,
}: ModalTabsProps) {
  if (defaultValue && value) throw new Error('Cannot provide both defaultValue and value');
  if (!defaultValue && !value) throw new Error('Must provide either defaultValue or value');

  return (
    <Tabs.Root
      className={tabsRootStyle}
      defaultValue={defaultValue}
      value={value}
      onValueChange={onValueChange}
    >
      <Tabs.List className={tabsListStyle}>
        <Flex direction="column" gap={20}>
          {headerContent}

          {tabGroups.map(({ title, tabs }, tabGroupIndex) => (
            <Flex direction="column" gap={8} key={`tab-group-${title ?? tabGroupIndex}`}>
              {title && (
                <Box px={8}>
                  <Text truncate as="div" fontSize="xs" color="tertiary" fontWeight="normal">
                    {title}
                  </Text>
                </Box>
              )}

              <Flex direction="column" gap={2}>
                {tabs
                  .filter(
                    (tab) =>
                      !tab.isHidden && (tab.isHiddenCallback ? !tab.isHiddenCallback() : true)
                  )
                  .map((tab, tabIndex) => (
                    <Tabs.Trigger
                      key={`tab-${tab.label ?? tabIndex}-${value}`}
                      className={tabsTriggerStyle}
                      value={tab.value}
                      data-testid={`settings-modal-${tab.label}-tab`}
                    >
                      {tab.kind === 'icon' && <Icon name={tab.icon} size="sm" />}
                      {tab.kind === 'image' && (
                        <span className={tabsIconImageContainerStyles}>
                          <img src={tab.src} className={tabsIconImageStyle} />
                        </span>
                      )}
                      {tab.label}
                    </Tabs.Trigger>
                  ))}
              </Flex>
            </Flex>
          ))}
        </Flex>
      </Tabs.List>

      {tabGroups.map(({ tabs, title }, index) =>
        tabs
          .filter((tab) => !tab.isHidden)
          .map(({ value, renderContent, label }) => (
            <Tabs.Content
              key={`tab-content-${title ?? index}-${value}`}
              className={tabsContentStyle}
              value={value}
            >
              {/* TODO: Consider using slot pattern here to disallow passing arbitrary components */}
              {renderContent({ label })}
            </Tabs.Content>
          ))
      )}
    </Tabs.Root>
  );
}
