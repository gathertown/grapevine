import React, { useCallback, useEffect, useRef, useState } from 'react';

import { horizontalThumbStyle, scrollbarTrackRecipe, verticalThumbStyle } from './Scrollable.css';

const SCROLLBAR_SIZE = 12;
const THUMB_INSET = 2;

export type ScrollbarsProps = {
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  scrollDirection: 'x' | 'y' | 'both';
  autoHide?: boolean;
};

export const Scrollbars = React.memo(function Scrollbars({
  scrollContainerRef,
  scrollDirection,
  autoHide = true,
}: ScrollbarsProps) {
  const [scrollState, setScrollState] = useState({
    scrollTop: 0,
    scrollLeft: 0,
    scrollHeight: 0,
    scrollWidth: 0,
    clientHeight: 0,
    clientWidth: 0,
  });

  const [isHovered, setIsHovered] = useState(false);
  const [isScrollbarHovered, setIsScrollbarHovered] = useState(false);
  const [isDragging, setIsDragging] = useState({ vertical: false, horizontal: false });

  const verticalThumbRef = useRef<HTMLDivElement | null>(null);
  const horizontalThumbRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef<{ vertical: boolean; horizontal: boolean }>({
    vertical: false,
    horizontal: false,
  });

  // Update scroll state when container scrolls.
  const updateScrollState = useCallback(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    setScrollState({
      scrollTop: scrollContainer.scrollTop,
      scrollLeft: scrollContainer.scrollLeft,
      scrollHeight: scrollContainer.scrollHeight,
      scrollWidth: scrollContainer.scrollWidth,
      clientHeight: scrollContainer.clientHeight,
      clientWidth: scrollContainer.clientWidth,
    });
  }, [scrollContainerRef]);

  // Listen for scroll events. This will include user-generated scrolls as well as scrolls caused by
  // content size shifts.
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    // Listen for scrolls.
    scrollContainer.addEventListener('scroll', updateScrollState);

    // Listen for resizes.
    const resizeObserver = new ResizeObserver(updateScrollState);
    resizeObserver.observe(scrollContainer);

    // Initial update.
    updateScrollState();

    return () => {
      scrollContainer.removeEventListener('scroll', updateScrollState);
      resizeObserver.disconnect();
    };
  }, [scrollContainerRef, updateScrollState]);

  // Listen for mouse events for auto-hide functionality.
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer || !autoHide) return;

    const handleMouseEnter = () => setIsHovered(true);
    const handleMouseLeave = () => setIsHovered(false);

    scrollContainer.addEventListener('mouseenter', handleMouseEnter);
    scrollContainer.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      scrollContainer.removeEventListener('mouseenter', handleMouseEnter);
      scrollContainer.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [scrollContainerRef, autoHide]);

  // Handle vertical thumb dragging.
  const handleVerticalMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDraggingRef.current.vertical = true;
      setIsDragging((prev) => ({ ...prev, vertical: true }));

      const scrollContainer = scrollContainerRef.current;
      if (!scrollContainer) return;

      const startY = e.clientY;
      const startScrollTop = scrollContainer.scrollTop;

      const handleMouseMove = (e: MouseEvent) => {
        if (!isDraggingRef.current.vertical) return;

        const deltaY = e.clientY - startY;
        const scrollRatio = deltaY / (scrollContainer.clientHeight - 40); // Account for thumb height
        const newScrollTop =
          startScrollTop +
          scrollRatio * (scrollContainer.scrollHeight - scrollContainer.clientHeight);

        scrollContainer.scrollTop = Math.max(
          0,
          Math.min(newScrollTop, scrollContainer.scrollHeight - scrollContainer.clientHeight)
        );
      };

      const handleMouseUp = () => {
        isDraggingRef.current.vertical = false;
        setIsDragging((prev) => ({ ...prev, vertical: false }));
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [scrollContainerRef]
  );

  // Handle horizontal thumb dragging.
  const handleHorizontalMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDraggingRef.current.horizontal = true;
      setIsDragging((prev) => ({ ...prev, horizontal: true }));

      const scrollContainer = scrollContainerRef.current;
      if (!scrollContainer) return;

      const startX = e.clientX;
      const startScrollLeft = scrollContainer.scrollLeft;

      const handleMouseMove = (e: MouseEvent) => {
        if (!isDraggingRef.current.horizontal) return;

        const deltaX = e.clientX - startX;
        const scrollRatio = deltaX / (scrollContainer.clientWidth - 40); // Account for thumb width
        const newScrollLeft =
          startScrollLeft +
          scrollRatio * (scrollContainer.scrollWidth - scrollContainer.clientWidth);

        scrollContainer.scrollLeft = Math.max(
          0,
          Math.min(newScrollLeft, scrollContainer.scrollWidth - scrollContainer.clientWidth)
        );
      };

      const handleMouseUp = () => {
        isDraggingRef.current.horizontal = false;
        setIsDragging((prev) => ({ ...prev, horizontal: false }));
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [scrollContainerRef]
  );

  // Calculate scrollbar visibility and dimensions.
  const hasVerticalScroll =
    (scrollDirection === 'y' || scrollDirection === 'both') &&
    scrollState.scrollHeight > scrollState.clientHeight;
  const hasHorizontalScroll =
    (scrollDirection === 'x' || scrollDirection === 'both') &&
    scrollState.scrollWidth > scrollState.clientWidth;

  // Calculate if we should even have a scrollbar for each dimension.
  const showVerticalScrollbar =
    hasVerticalScroll && (!autoHide || isHovered || isScrollbarHovered || isDragging.vertical);
  const showHorizontalScrollbar =
    hasHorizontalScroll && (!autoHide || isHovered || isScrollbarHovered || isDragging.horizontal);

  // Calculate the vertical scrollbar height and thumb position.
  const availableVerticalTrackHeight = showHorizontalScrollbar
    ? scrollState.clientHeight - SCROLLBAR_SIZE
    : scrollState.clientHeight;
  const verticalThumbHeight = Math.max(
    20,
    (scrollState.clientHeight / scrollState.scrollHeight) * scrollState.clientHeight
  );
  const verticalThumbTop =
    THUMB_INSET +
    (scrollState.scrollTop / (scrollState.scrollHeight - scrollState.clientHeight)) *
      (availableVerticalTrackHeight - verticalThumbHeight - THUMB_INSET * 2);

  // Calculate the horizontal scrollbar width and thumb position.
  const availableHorizontalTrackWidth = showVerticalScrollbar
    ? scrollState.clientWidth - SCROLLBAR_SIZE
    : scrollState.clientWidth;
  const horizontalThumbWidth = Math.max(
    20,
    (scrollState.clientWidth / scrollState.scrollWidth) * scrollState.clientWidth
  );
  const horizontalThumbLeft =
    THUMB_INSET +
    (scrollState.scrollLeft / (scrollState.scrollWidth - scrollState.clientWidth)) *
      (availableHorizontalTrackWidth - horizontalThumbWidth - THUMB_INSET * 2);

  return (
    <>
      {/* Vertical Scrollbar */}
      {hasVerticalScroll && (
        <div
          className={scrollbarTrackRecipe({
            direction: 'vertical',
            autoHide: autoHide && !showVerticalScrollbar,
            visible: showVerticalScrollbar,
          })}
          style={{
            top: 0,
            bottom: hasHorizontalScroll ? SCROLLBAR_SIZE : 0,
          }}
          onMouseEnter={() => setIsScrollbarHovered(true)}
          onMouseLeave={() => setIsScrollbarHovered(false)}
        >
          <div
            ref={verticalThumbRef}
            onMouseDown={handleVerticalMouseDown}
            className={verticalThumbStyle}
            style={{
              top: verticalThumbTop,
              height: verticalThumbHeight,
            }}
          />
        </div>
      )}

      {/* Horizontal Scrollbar */}
      {hasHorizontalScroll && (
        <div
          className={scrollbarTrackRecipe({
            direction: 'horizontal',
            autoHide: autoHide && !showHorizontalScrollbar,
            visible: showHorizontalScrollbar,
          })}
          style={{
            left: 0,
            right: hasVerticalScroll ? SCROLLBAR_SIZE : 0,
          }}
          onMouseEnter={() => setIsScrollbarHovered(true)}
          onMouseLeave={() => setIsScrollbarHovered(false)}
        >
          <div
            ref={horizontalThumbRef}
            onMouseDown={handleHorizontalMouseDown}
            className={horizontalThumbStyle}
            style={{
              left: horizontalThumbLeft,
              width: horizontalThumbWidth,
            }}
          />
        </div>
      )}
    </>
  );
});
