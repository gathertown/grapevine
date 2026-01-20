import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { SmartStringSearchUtil } from '../../../utils/smartSearch';
import { IconButton } from '../../base/IconButton/IconButton';
import { Text } from '../../base/Text/Text';
import { Flex } from '../../layout/Flex/Flex';
import * as styles from './SearchableDropdown.css';
import { useKeyboardNavigation } from './useKeyboardNavigation';

export interface SearchableDropdownSection<T> {
  title: string;
  items: T[];
}

export interface SearchableDropdownSpecialItem {
  id: string;
  render: () => React.ReactNode;
  onClick: () => void;
}

export interface SearchableDropdownProps<T> {
  // Input props
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;

  // Validation
  validateInput?: (input: string) => boolean;
  validationErrorMessage?: string;
  showError?: boolean;

  // Data & rendering
  items?: T[];
  sections?: SearchableDropdownSection<T>[];
  specialItems?: SearchableDropdownSpecialItem[];
  renderItem: (item: T, isSelected: boolean, isHighlighted: boolean) => React.ReactNode;
  getItemKey: (item: T) => string;
  getSearchText: (item: T) => string;
  getSearchKeywords?: (item: T) => string[];
  maxItems?: number;

  // Selection
  selectedItem?: T;
  onSelect: (item: T) => void;

  // Actions
  onAddNew?: (input: string) => void;
  onClose?: () => void;

  // Custom content when search is active (overrides normal rendering)
  searchActiveContent?: (searchValue: string) => React.ReactNode;

  // Empty state
  emptyStateRender?: () => React.ReactNode;
  onEmptyStateClick?: () => void;

  // Styling
  width?: number;
  minHeight?: number;
  maxHeight?: number;

  // Behavior
  closeOnSelect?: boolean;
  enableKeyboardNavigation?: boolean;
  autoFocus?: boolean;
}

export function SearchableDropdown<T>({
  searchPlaceholder = 'Search...',
  searchValue = '',
  onSearchChange,
  validateInput,
  validationErrorMessage,
  showError = false,
  items = [],
  sections = [],
  specialItems = [],
  renderItem,
  getItemKey,
  getSearchText,
  getSearchKeywords,
  maxItems,
  selectedItem,
  onSelect,
  onAddNew,
  onClose,
  searchActiveContent,
  emptyStateRender,
  onEmptyStateClick,
  width = 218,
  minHeight,
  maxHeight = 318,
  closeOnSelect = true,
  enableKeyboardNavigation = true,
  autoFocus = true,
}: SearchableDropdownProps<T>) {
  const [internalSearchValue, setInternalSearchValue] = useState(searchValue);
  const [isKeyboardMode, setIsKeyboardMode] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentSearchValue = onSearchChange ? searchValue : internalSearchValue;

  const handleSearchChange = useCallback(
    (value: string) => {
      if (onSearchChange) {
        onSearchChange(value);
      } else {
        setInternalSearchValue(value);
      }
    },
    [onSearchChange]
  );

  // Filter items using SmartStringSearchUtil
  const filteredItems = useMemo(() => {
    if (!currentSearchValue) return items.slice(0, maxItems || items.length);

    return SmartStringSearchUtil.searchCollection(currentSearchValue, items, (item) => ({
      title: getSearchText(item),
      keywords: getSearchKeywords ? getSearchKeywords(item) : [],
      enableMultiTermSearch: true,
    })).slice(0, maxItems || items.length);
  }, [items, currentSearchValue, getSearchText, maxItems, getSearchKeywords]);

  // Filter sections using SmartStringSearchUtil
  const filteredSections = useMemo(() => {
    if (!currentSearchValue) return sections;

    return sections
      .map((section) => ({
        ...section,
        items: SmartStringSearchUtil.searchCollection(
          currentSearchValue,
          section.items,
          (item) => ({
            title: getSearchText(item),
          })
        ),
      }))
      .filter((section) => section.items.length > 0);
  }, [sections, currentSearchValue, getSearchText]);

  // Calculate total number of selectable items for keyboard navigation
  const totalSelectableCount = useMemo(
    () =>
      specialItems.length +
      filteredItems.length +
      filteredSections.reduce((acc, section) => acc + section.items.length, 0),
    [specialItems.length, filteredItems.length, filteredSections]
  );

  // Create a flat list of renderable items with metadata
  type RenderableItem =
    | { type: 'special'; item: SearchableDropdownSpecialItem; index: number; id: string }
    | { type: 'standalone'; item: T; index: number; id: string }
    | { type: 'section-header'; title: string; index: number; id: string }
    | { type: 'section-item'; item: T; index: number; id: string };

  const renderableItems = useMemo((): RenderableItem[] => {
    const items: RenderableItem[] = [];
    let currentIndex = 0;

    // Add special items
    specialItems.forEach((specialItem) => {
      items.push({
        type: 'special',
        item: specialItem,
        index: currentIndex++,
        id: specialItem.id,
      });
    });

    // Add standalone items
    filteredItems.forEach((item) => {
      items.push({
        type: 'standalone',
        item,
        index: currentIndex++,
        id: getItemKey(item),
      });
    });

    // Add section items
    filteredSections.forEach((section) => {
      // Section headers are not selectable, don't increment index
      items.push({
        type: 'section-header',
        title: section.title,
        index: -1, // Not selectable
        id: `section-${section.title}`,
      });

      section.items.forEach((item) => {
        items.push({
          type: 'section-item',
          item,
          index: currentIndex++,
          id: getItemKey(item),
        });
      });
    });

    return items;
  }, [specialItems, filteredItems, filteredSections, getItemKey]);

  // Extract selectable items for keyboard navigation
  const allSelectableItems = useMemo(
    () =>
      renderableItems
        .filter((item) => item.type !== 'section-header')
        .map((item) => {
          if (item.type === 'special') return null;
          return item.item;
        })
        .filter((item): item is T => item !== null),
    [renderableItems]
  );

  const {
    highlightedIndex,
    setHighlightedIndex,
    handleKeyDown,
    scrollContainerRef,
    setHighlightedRef,
  } = useKeyboardNavigation(totalSelectableCount, (index: number) => {
    // Handle special items first
    if (index < specialItems.length) {
      specialItems[index]?.onClick();
      return;
    }

    // Handle regular items
    const regularItemIndex = index - specialItems.length;
    const item = allSelectableItems[regularItemIndex];
    if (item) {
      onSelect(item);
      if (closeOnSelect && onClose) {
        onClose();
      }
    }
  });

  // Reset highlighted index when items change
  useEffect(() => {
    setHighlightedIndex(0);
  }, [totalSelectableCount, setHighlightedIndex]);

  // Auto focus the input
  useEffect(() => {
    if (autoFocus && inputRef.current) {
      inputRef.current.focus();
    }
  }, [autoFocus]);

  const handleInputKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (onClose) {
          onClose();
        }
        return;
      }

      if (event.key === 'Enter' && onAddNew && currentSearchValue) {
        const isValid = !validateInput || validateInput(currentSearchValue);
        if (isValid) {
          event.preventDefault();
          onAddNew(currentSearchValue);
          return;
        }
      }

      if (enableKeyboardNavigation && totalSelectableCount > 0) {
        // Enter keyboard mode when using arrow keys or tab
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Tab') {
          setIsKeyboardMode(true);
        }
        handleKeyDown(event);
      }
    },
    [
      currentSearchValue,
      onAddNew,
      validateInput,
      onClose,
      enableKeyboardNavigation,
      totalSelectableCount,
      handleKeyDown,
    ]
  );

  const handleClearSearch = useCallback(() => {
    handleSearchChange('');
    if (onEmptyStateClick) {
      onEmptyStateClick();
    }
  }, [handleSearchChange, onEmptyStateClick]);

  // Composable render helpers
  const renderSpecialItem = (renderableItem: RenderableItem & { type: 'special' }) => {
    const { item: specialItem, index } = renderableItem;
    const isHighlighted = enableKeyboardNavigation && index === highlightedIndex;
    const baseClassName = isKeyboardMode ? styles.dropdownItemKeyboardMode : styles.dropdownItem;

    return (
      <div
        key={specialItem.id}
        ref={isHighlighted ? setHighlightedRef : null}
        className={isHighlighted ? styles.dropdownItemHighlighted : baseClassName}
        onClick={specialItem.onClick}
        onMouseEnter={() => {
          if (enableKeyboardNavigation) {
            setIsKeyboardMode(false);
            setHighlightedIndex(index);
          }
        }}
      >
        {specialItem.render()}
      </div>
    );
  };

  const renderStandaloneItem = (renderableItem: RenderableItem & { type: 'standalone' }) => {
    const { item, index } = renderableItem;
    const isSelected = selectedItem ? getItemKey(selectedItem) === getItemKey(item) : false;
    const isHighlighted = enableKeyboardNavigation && index === highlightedIndex;
    const baseClassName = isKeyboardMode ? styles.dropdownItemKeyboardMode : styles.dropdownItem;

    return (
      <div
        key={getItemKey(item)}
        ref={isHighlighted ? setHighlightedRef : null}
        className={isHighlighted ? styles.dropdownItemHighlighted : baseClassName}
        onClick={() => {
          onSelect(item);
          if (closeOnSelect && onClose) {
            onClose();
          }
        }}
        onMouseEnter={() => {
          if (enableKeyboardNavigation) {
            setIsKeyboardMode(false);
            setHighlightedIndex(index);
          }
        }}
      >
        {renderItem(item, isSelected, isHighlighted)}
      </div>
    );
  };

  const renderSectionHeader = (renderableItem: RenderableItem & { type: 'section-header' }) => (
    <Flex key={renderableItem.id} gap={8} p={8}>
      <Text fontSize="xs" fontWeight="semibold" color="primary">
        {renderableItem.title}
      </Text>
    </Flex>
  );

  const renderSectionItem = (renderableItem: RenderableItem & { type: 'section-item' }) => {
    const { item, index } = renderableItem;
    const isSelected = selectedItem ? getItemKey(selectedItem) === getItemKey(item) : false;
    const isHighlighted = enableKeyboardNavigation && index === highlightedIndex;
    const baseClassName = isKeyboardMode ? styles.dropdownItemKeyboardMode : styles.dropdownItem;

    return (
      <div
        key={getItemKey(item)}
        ref={isHighlighted ? setHighlightedRef : null}
        className={isHighlighted ? styles.dropdownItemHighlighted : baseClassName}
        onClick={() => {
          onSelect(item);
          if (closeOnSelect && onClose) {
            onClose();
          }
        }}
        onMouseEnter={() => {
          if (enableKeyboardNavigation) {
            setIsKeyboardMode(false);
            setHighlightedIndex(index);
          }
        }}
      >
        {renderItem(item, isSelected, isHighlighted)}
      </div>
    );
  };

  const renderEmptyState = () => {
    if (totalSelectableCount > 0 || !emptyStateRender) return null;

    return <div onClick={onEmptyStateClick}>{emptyStateRender()}</div>;
  };

  const renderCurrentContent = () => {
    // Show custom search content if provided and search is active
    if (searchActiveContent && currentSearchValue) return searchActiveContent(currentSearchValue);

    return (
      <>
        {renderableItems.map((item) => {
          switch (item.type) {
            case 'special':
              return renderSpecialItem(item);
            case 'standalone':
              return renderStandaloneItem(item);
            case 'section-header':
              return renderSectionHeader(item);
            case 'section-item':
              return renderSectionItem(item);
            default:
              return null;
          }
        })}
        {renderEmptyState()}
      </>
    );
  };

  return (
    <div className={styles.container} style={{ width, minHeight, maxHeight }}>
      <div className={styles.inputContainer}>
        <input
          ref={inputRef}
          type="text"
          placeholder={searchPlaceholder}
          value={currentSearchValue}
          onChange={(e) => handleSearchChange(e.target.value)}
          onKeyDown={handleInputKeyDown}
          className={showError ? styles.inputError : styles.input}
        />
        {currentSearchValue && (
          <div className={styles.clearButton}>
            <IconButton icon="close" size="xs" kind="transparent" onClick={handleClearSearch} />
          </div>
        )}
      </div>

      {showError && validationErrorMessage && (
        <div className={styles.errorMessage}>
          <Text fontSize="xs" color="dangerPrimary">
            {validationErrorMessage}
          </Text>
        </div>
      )}

      <div ref={scrollContainerRef} className={styles.scrollContainer}>
        {renderCurrentContent()}
      </div>
    </div>
  );
}
