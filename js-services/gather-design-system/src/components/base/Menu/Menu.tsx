import * as MenuPrimitive from '@radix-ui/react-dropdown-menu';
import React, { useMemo } from 'react';

import { isNil } from '../../../utils/fpHelpers';
import { usePortalContainer } from '../../../helpers/usePortalContainer';
import { Gothify } from '../../../providers/Gothify';
import { Icon, IconName } from '../Icon/Icon';
import { KeyboardShortcut, KeyboardShortcutProps } from '../KeyboardShortcut/KeyboardShortcut';
import { textColorStyles } from '../Text/Text.css';
import {
  arrowFillStyle,
  contentStyle,
  itemRecipe,
  keyboardShortcutStyle,
  labelStyle,
  radioItemIndicatorStyle,
  scrollableContainerStyle,
  separatorStyle,
} from './Menu.css';

const MenuRoot = MenuPrimitive.Root;
MenuRoot.displayName = 'Menu';

// ============= ITEM ============= //
const MenuGroup = MenuPrimitive.Group;
MenuGroup.displayName = 'Menu.Group';

export type MenuItemProps = Omit<MenuPrimitive.DropdownMenuItemProps, 'className'> & {
  icon?: IconName;
  keyboardShortcut?: KeyboardShortcutProps['keys'];
  skipRaf?: boolean;
  color?: keyof typeof textColorStyles;
};

const MenuItem = React.memo(function MenuItem({
  children,
  icon,
  onSelect,
  keyboardShortcut,
  skipRaf,
  color,
  ...props
}: MenuItemProps) {
  const handleSelect = (event: Event) => {
    if (!onSelect) return;

    // TODO(ds): determine if we still the raf & skipRaf property
    if (skipRaf) {
      onSelect(event);
    } else {
      // Address potential race between Radix UI components with overlays
      // https://github.com/gathertown/gather-town-v2/pull/2404/files#r1874599241
      requestAnimationFrame(() => {
        onSelect(event);
      });
    }
  };
  return (
    <MenuPrimitive.Item className={itemRecipe({ color })} {...props} onSelect={handleSelect}>
      {icon && <Icon name={icon} size="sm" />}
      {children}
      {keyboardShortcut && (
        <div className={keyboardShortcutStyle}>
          <KeyboardShortcut size="sm" keys={keyboardShortcut} />
        </div>
      )}
    </MenuPrimitive.Item>
  );
});
MenuItem.displayName = 'Menu.Item';

// ============= RADIO ============= //

const MenuRadioGroup = MenuPrimitive.RadioGroup;

MenuRadioGroup.displayName = 'Menu.RadioGroup';

const MenuRadioItem = React.memo(
  React.forwardRef<HTMLDivElement, MenuPrimitive.DropdownMenuRadioItemProps>(function MenuRadioItem(
    { children, ...props },
    ref
  ) {
    return (
      <MenuPrimitive.RadioItem ref={ref} className={itemRecipe()} {...props}>
        <MenuPrimitive.ItemIndicator className={radioItemIndicatorStyle}>
          <Icon name="check" size="sm" color="accentSecondary" />
        </MenuPrimitive.ItemIndicator>
        {children}
      </MenuPrimitive.RadioItem>
    );
  })
);
MenuRadioItem.displayName = 'Menu.RadioItem';

// ============= CHECKBOX ============= //

const MenuCheckboxItem = React.memo(
  React.forwardRef<
    HTMLDivElement,
    MenuPrimitive.DropdownMenuCheckboxItemProps & { icon?: IconName }
  >(function MenuCheckboxItem({ children, icon, ...props }, ref) {
    return (
      <MenuPrimitive.CheckboxItem ref={ref} className={itemRecipe()} {...props}>
        {icon && <Icon name={icon} size="sm" />}
        {children}
      </MenuPrimitive.CheckboxItem>
    );
  })
);
MenuCheckboxItem.displayName = 'Menu.CheckboxItem';

// ============= SEPARATOR ============= //

const MenuSeparator = React.memo(function MenuSeparator() {
  return <MenuPrimitive.Separator className={separatorStyle} />;
});
MenuSeparator.displayName = 'Menu.Separator';

// ============= LABEL ============= //

const MenuLabel = React.memo(function MenuLabel(props: MenuPrimitive.DropdownMenuLabelProps) {
  return <MenuPrimitive.Label className={labelStyle} {...props} />;
});
MenuLabel.displayName = 'Menu.Label';

// ============= TRIGGER ============= //

const MenuTrigger = React.memo(
  React.forwardRef<HTMLButtonElement, MenuPrimitive.DropdownMenuTriggerProps>(
    function MenuTrigger(props, forwardedRef) {
      return <MenuPrimitive.Trigger asChild {...props} ref={forwardedRef} />;
    }
  )
);
MenuTrigger.displayName = 'Menu.Trigger';

// ============= CONTENT ============= //

export interface MenuContentProps {
  children: React.ReactNode;
  side?: MenuPrimitive.DropdownMenuContentProps['side'];
  align?: MenuPrimitive.DropdownMenuContentProps['align'];
  withArrow?: boolean;
  collisionPadding?: MenuPrimitive.DropdownMenuContentProps['collisionPadding'];
  portalContainerId?: string;
  theme?: 'dark' | 'light';
  sideOffset?: MenuPrimitive.DropdownMenuContentProps['sideOffset'];
  alignOffset?: MenuPrimitive.DropdownMenuContentProps['alignOffset'];
  // In Radix dropdown menus, the trigger is automatically focused when the menu is closed.
  // https://www.radix-ui.com/primitives/docs/components/dropdown-menu#content (onCloseAutoFocus)
  // This flag allows us to prevent that behavior.
  preventAutoFocusTriggerOnClose?: boolean;
  width?: number | 'auto';
  maxWidth?: number;
  color?: keyof typeof textColorStyles;
}

const MenuContent = React.memo(
  React.forwardRef<HTMLDivElement, MenuContentProps>(function MenuContent(
    {
      children,
      portalContainerId,
      withArrow = true,
      sideOffset = 6,
      alignOffset = 0,
      width,
      maxWidth,
      theme = 'dark',
      preventAutoFocusTriggerOnClose = false,
      ...props
    },
    forwardedRef
  ) {
    const container = usePortalContainer(portalContainerId);

    const items: React.ReactElement[] = useMemo(
      () =>
        React.Children.toArray(children)
          .filter((child) => !isNil(child) && React.isValidElement(child))
          .flatMap((child, index) =>
            child.type === MenuGroup && index > 0
              ? // add a separator between each group of items if they actually exist
                [<Menu.Separator key={`separator-${index}`} />, child]
              : [child]
          ),
      [children]
    );

    return (
      <MenuPrimitive.Portal container={container}>
        <Gothify enabled={theme === 'dark'}>
          <MenuPrimitive.Content
            className={contentStyle}
            sideOffset={sideOffset}
            alignOffset={alignOffset}
            arrowPadding={16}
            {...props}
            ref={forwardedRef}
            onCloseAutoFocus={(e) => {
              if (preventAutoFocusTriggerOnClose) {
                e.preventDefault();
              }
            }}
            style={{
              width,
              maxWidth,
            }}
          >
            <div className={scrollableContainerStyle}>{items}</div>
            {withArrow && <MenuPrimitive.Arrow className={arrowFillStyle} />}
          </MenuPrimitive.Content>
        </Gothify>
      </MenuPrimitive.Portal>
    );
  })
);
MenuContent.displayName = 'Menu.Content';

export interface MenuProps extends MenuPrimitive.DropdownMenuProps {}

// TODO [APP-8949]: Migrate to assignSlots
export const Menu = Object.assign(MenuRoot, {
  Trigger: MenuTrigger,
  Content: MenuContent,
  Item: MenuItem,
  RadioGroup: MenuRadioGroup,
  RadioItem: MenuRadioItem,
  CheckboxItem: MenuCheckboxItem,
  Separator: MenuSeparator,
  Label: MenuLabel,
  Group: MenuGroup,
});
