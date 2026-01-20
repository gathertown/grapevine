// This barrel export is a special exception for gather-design-system to fix auto-imports
// See this PR for more details: https://github.com/gathertown/gather-town-v2/pull/1794

// Base components
export { Avatar } from './components/base/Avatar/Avatar';
export { AvatarGroup } from './components/base/AvatarGroup/AvatarGroup';
export { AvatarGroupByAvailability } from './components/base/AvatarGroupByAvailability/AvatarGroupByAvailability';
export { Badge } from './components/base/Badge/Badge';
export { Button } from './components/base/Button/Button';
export { Clickable } from './components/base/Clickable/Clickable';
export { Divider } from './components/base/Divider/Divider';
export { Icon } from './components/base/Icon/Icon';
export { IconButton } from './components/base/IconButton/IconButton';
export { Indicator } from './components/base/Indicator/Indicator';
export { PositionedIndicator } from './components/base/Indicator/PositionedIndicator';
export { KeyboardShortcut } from './components/base/KeyboardShortcut/KeyboardShortcut';
export { Loader } from './components/base/Loader/Loader';
export { Menu } from './components/base/Menu/Menu';
export { Modal } from './components/base/Modal/Modal';
export { ModalTabs } from './components/base/ModalTabs/ModalTabs';
export { Popover } from './components/base/Popover/Popover';
export { ResizablePanel } from './components/base/ResizablePanel/ResizablePanel';
export { SegmentedControl } from './components/base/SegmentedControl/SegmentedControl';
export { Slider } from './components/base/Slider/Slider';
export { StatusIndicator, StatusIndicatorKind } from './components/base/Status/StatusIndicator';
export { Text } from './components/base/Text/Text';
export { Tooltip } from './components/base/Tooltip/Tooltip';
export { VirtualList, type VirtualListHandle } from './components/base/VirtualList/VirtualList';
export { MultiSelect } from './components/features/chat/MultiSelect/MultiSelect';

// Form components
export { Checkbox } from './components/form/Checkbox/Checkbox';
export { Input } from './components/form/Input/Input';
export { Label } from './components/form/Label/Label';
export { RadioGroup, RadioGroupItem } from './components/form/RadioGroup/RadioGroup';
export { SearchableDropdown } from './components/form/SearchableDropdown/SearchableDropdown';
export { Select } from './components/form/Select/Select';
export { TextArea } from './components/form/TextArea/TextArea';
export { ToggleSwitch } from './components/form/ToggleSwitch/ToggleSwitch';

// Layout components
export { Box } from './components/layout/Box/Box';
export { Container } from './components/layout/Container/Container';
export { Flex } from './components/layout/Flex/Flex';
export { Scrollable } from './components/layout/Scrollable/Scrollable';

// Feature components
export {
  ChatMention,
  ChatMentionContext,
  ChatMentionProvider,
} from './components/features/chat/ChatMention/ChatMention';
export { MessageComposer } from './components/features/chat/MessageComposer/MessageComposer';
export { messageContentStyle } from './components/features/chat/MessageComposer/MessageComposer.css';
export { MessageComposerExtension } from './components/features/chat/MessageComposer/messageComposerConfig';
export { TransientMessageComposer } from './components/features/chat/TransientMessageComposer/TransientMessageComposer';

// Theming
export { FloatingContainerContext } from './helpers/FloatingContainerContext';
export { Gothify } from './providers/Gothify';
export { ThemeProvider } from './providers/ThemeProvider';
export { colorMode } from './providers/ThemeProvider.css';

// Types
export type { AvatarProps } from './components/base/Avatar/Avatar';
export type { AvatarGroupProps } from './components/base/AvatarGroup/AvatarGroup';
export type { ButtonProps } from './components/base/Button/Button';
export type { IconName, IconProps } from './components/base/Icon/Icon';
export type { IconButtonProps } from './components/base/IconButton/IconButton';
export type { GenericKeyboardKey } from './components/base/KeyboardShortcut/KeyboardShortcut';
export type { KeyboardKey } from './components/base/KeyboardShortcut/KeyboardTypes';
export type { ModalProps } from './components/base/Modal/Modal';
export type { ModalTabConfig, ModalTabsProps } from './components/base/ModalTabs/ModalTabs';
export type { StatusIndicatorProps } from './components/base/Status/StatusIndicator';
export type { VirtualListProps } from './components/base/VirtualList/VirtualList';
export type {
  ChannelMentionMap,
  UserGroupMentionMap,
  UserMentionMap,
} from './components/features/chat/ChatMention/ChatMention';
export type { MessageComposerProps } from './components/features/chat/MessageComposer/MessageComposer';
export type { MessageComposerRef } from './components/features/chat/MessageComposer/MessageComposer';
export type {
  SearchableDropdownProps,
  SearchableDropdownSection,
  SearchableDropdownSpecialItem,
} from './components/form/SearchableDropdown/SearchableDropdown';
export type { SelectOption, SelectProps } from './components/form/Select/Select';
export type { TextAreaProps } from './components/form/TextArea/TextArea';
export type { BoxProps } from './components/layout/Box/Box';
export type { FlexProps } from './components/layout/Flex/Flex';
export type { AvatarItem } from './helpers/avatars';
export type { JSONContent } from '@tiptap/core';

// Styles
export { disabledAnimations } from './styles/reusableStyles.css';

// Helpers
export { isRadixElement } from './helpers/isRadixElement';
