import { useCallback, useEffect, useRef, useState } from 'react';

export function useKeyboardNavigation(size: number, onSelect: (index: number) => void) {
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const highlightedElementRef = useRef<HTMLDivElement>(null);

  const setHighlightedRef = useCallback((element: HTMLDivElement | null) => {
    highlightedElementRef.current = element;
  }, []);

  const scrollToHighlighted = useCallback(() => {
    const scrollContainer = scrollContainerRef.current;
    const highlightedElement = highlightedElementRef.current;

    if (!scrollContainer || !highlightedElement) return;

    const containerRect = scrollContainer.getBoundingClientRect();
    const elementRect = highlightedElement.getBoundingClientRect();

    const elementTop = elementRect.top - containerRect.top + scrollContainer.scrollTop;
    const elementBottom = elementTop + elementRect.height;

    const containerScrollTop = scrollContainer.scrollTop;
    const containerScrollBottom = containerScrollTop + containerRect.height;

    // Scroll if element is above or below visible area
    if (elementTop < containerScrollTop) {
      scrollContainer.scrollTop = elementTop;
    } else if (elementBottom > containerScrollBottom) {
      scrollContainer.scrollTop = elementBottom - containerRect.height;
    }
  }, []);

  useEffect(() => {
    scrollToHighlighted();
  }, [highlightedIndex, scrollToHighlighted]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (size === 0) return;

    switch (event.key) {
      case 'ArrowDown':
      case 'Tab':
        event.preventDefault();
        setHighlightedIndex((prev) => (prev + 1) % size);
        break;
      case 'ArrowUp':
        event.preventDefault();
        setHighlightedIndex((prev) => (prev - 1 + size) % size);
        break;
      case 'Enter':
        event.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < size) {
          onSelect(highlightedIndex);
        }
        break;
    }
  };

  return {
    setHighlightedIndex,
    highlightedIndex,
    handleKeyDown,
    scrollContainerRef,
    setHighlightedRef,
  };
}
