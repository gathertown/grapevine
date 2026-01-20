import {
  useVirtualizer,
  VirtualItem,
  Virtualizer,
  VirtualizerOptions,
} from '@tanstack/react-virtual';
import React, {
  ReactNode,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
} from 'react';

import { doIt } from '../../../utils/fpHelpers';
import { Scrollable } from '../../layout/Scrollable/Scrollable';

// Export the imperative handle type so consumers can use it.
export type VirtualListHandle = {
  scrollToOffset: (offset: number) => void;
  scrollToBottom: () => void;
  scrollToIndex: (index: number) => void;
};

export type VirtualListProps = {
  /**
   * The total number of items in the list.
   */
  totalItems: number;

  /**
   * For internal caching purposes, it's useful to have a unique id for each item rather than an
   * index. This allows for stable item heights in Tanstack Virtual's measurement cache even when
   * the index causes items to shift. Note: this is just a pass-through straight to the virtualizer.
   */
  getItemKey?: (index: number) => string;

  /**
   * Optional map of item indices to version keys for cache-busting. When provided, the version will
   * be included in the item key to force re-rendering when the version changes.
   */
  versionKeyMap?: Record<number, string | number>;

  /**
   * Function to render an item in the list.
   */
  renderItem: (index: number) => ReactNode;

  /**
   * The height of each item in the list (in pixels). This can be:
   * - A fixed number for all items
   * - A function that returns a height for a specific item
   * - An initial estimate when using dynamicSize=true
   */
  itemHeight: number | ((index: number) => number);

  /**
   * Use dynamic measurement for item heights. When true, items will be measured after rendering.
   * This is useful when items have variable heights that can't be determined ahead of time.
   * The itemHeight is used as an initial estimate before measurement.
   */
  dynamicSize?: boolean;

  /**
   * Optional direction for the list. When "bottom-up", the list will be anchored to the bottom and
   * new items will appear from the bottom Useful for chat-like interfaces
   */
  direction?: 'top-down' | 'bottom-up';

  /**
   * Additional options to pass to the TanStack virtualizer.
   */
  virtualizerOptions?: Partial<VirtualizerOptions<HTMLDivElement, Element>>;

  /**
   * Callback fired when the visible items in the viewport change. Provides the range of visible
   * items as [startIndex, endIndex].
   */
  onVisibleItemsChange?: (visibleRange: [number, number]) => void;

  /**
   * Callback fired when one of either "at top" or "at bottom" changes status (when entering or
   * leaving those states).
   */
  onScrolledBoundaryChanged?: (boundaries: { isAtTop: boolean; isAtBottom: boolean }) => void;

  /**
   * Callback fired when the content container height changes. Useful for detecting when
   * virtual list content has settled after loading new data.
   */
  onContentResize?: () => void;

  /**
   * Ref for imperative control of the VirtualList.
   */
  ref?: React.Ref<VirtualListHandle>;
};

const SCROLL_BOUNDARY_THRESHOLD = 10;
const SCROLLABLE_STYLE = { display: 'flex', flexDirection: 'column' } as const;

export const VirtualList = React.memo(function VirtualList({
  totalItems,
  renderItem,
  itemHeight,
  direction = 'top-down',
  dynamicSize = false,
  virtualizerOptions = {},
  onVisibleItemsChange,
  onScrolledBoundaryChanged,
  onContentResize,
  getItemKey,
  versionKeyMap,
  ref,
}: VirtualListProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const contentContainerRef = useRef<HTMLDivElement | null>(null);

  // Control whether to pin scroll to bottom. Used by usePinScrollToBottom hook.
  const pinScrollToBottomRef = useRef(false);

  // Tanstack Virtual does most of the heavy lifting.
  const virtualizer = useVirtualizer({
    count: totalItems,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: (index: number) =>
      typeof itemHeight === 'number' ? itemHeight : itemHeight(index),
    measureElement: dynamicSize
      ? (element: Element) => element.getBoundingClientRect().height
      : undefined,
    getItemKey,
    ...virtualizerOptions,
  });

  // Create a handler for delegate methods.
  const scrollMethods = useMemo(
    () => ({
      scrollToOffset: (offset: number) => {
        pinScrollToBottomRef.current = false;

        virtualizer.scrollToOffset(offset, { behavior: 'auto' });
      },
      scrollToBottom: () => {
        const totalSize = virtualizer.getTotalSize();
        virtualizer.scrollToOffset(totalSize, {
          align: 'end',
          behavior: 'auto',
        });
      },
      scrollToIndex: (index: number) => {
        pinScrollToBottomRef.current = false;

        virtualizer.scrollToIndex(index, {
          align: 'center',
          behavior: 'auto',
        });
      },
    }),
    [virtualizer]
  );

  // Expose imperative methods through ref.
  useImperativeHandle(ref, () => scrollMethods, [scrollMethods]);

  // Create a scroll handler that calls onScrolledBoundaryChanged when boundaries change. We can't
  // just use an onScroll subscription because scroll events are triggered by resizes and scroll
  // pinning.
  const handleUserScroll = useScrolledBoundaryChanged(onScrolledBoundaryChanged);

  // Pull the DOM nodes off the refs for use in effects.
  const scrollContainer = scrollContainerRef.current;
  const contentContainer = contentContainerRef.current;

  // Scroll anchoring for paginated data (when getItemKey is provided).
  useScrollAnchor({
    enabled: !!getItemKey,
    count: totalItems,
    virtualizer,
    scrollContainer,
    direction,
  });

  // Pin the scrollbar to the bottom for bottom-up lists.
  usePinScrollToBottom({
    enabled: direction === 'bottom-up',
    scrollContainer,
    contentContainer,
    onUserScroll: handleUserScroll,
    onContentResize,
    pinScrollToBottomRef,
  });

  // Notify parent when visible range changes.
  useVisibleItemsChanged({
    direction,
    virtualizer,
    onVisibleItemsChange,
    totalItems,
  });

  // Call onScrolledBoundaryChanged with initial boundary state on mount.
  useLayoutEffect(() => {
    if (!scrollContainer || !onScrolledBoundaryChanged) return;

    const isAtTop = scrollContainer.scrollTop <= SCROLL_BOUNDARY_THRESHOLD;
    const isAtBottom =
      scrollContainer.scrollTop + scrollContainer.offsetHeight >=
      scrollContainer.scrollHeight - SCROLL_BOUNDARY_THRESHOLD;

    onScrolledBoundaryChanged({ isAtTop, isAtBottom });
  }, [onScrolledBoundaryChanged, scrollContainer]);

  return (
    <Scrollable ref={scrollContainerRef} scrollDirection="y" style={SCROLLABLE_STYLE}>
      <div
        ref={contentContainerRef}
        style={{
          height: virtualizer.getTotalSize(),
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem: VirtualItem) => {
          const index = virtualItem.index;

          return (
            <div
              key={`${virtualItem.key}-${versionKeyMap?.[index] ?? ''}`}
              data-index={index}
              ref={dynamicSize ? virtualizer.measureElement : undefined}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: dynamicSize ? 'auto' : `${virtualItem.size}px`,
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              {renderItem(index)}
            </div>
          );
        })}
      </div>
    </Scrollable>
  );
});

function useVisibleItemsChanged({
  direction,
  virtualizer,
  onVisibleItemsChange,
  totalItems,
}: {
  direction: 'bottom-up' | 'top-down';
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  onVisibleItemsChange?: (visibleRange: [number, number]) => void;
  totalItems: number;
}) {
  // Get the current visible range directly from the virtualizer.
  const visibleIndexes = virtualizer.getVirtualIndexes();
  const startIndex = visibleIndexes.at(0) ?? null;
  const endIndex = visibleIndexes.at(-1) ?? null;

  // Make sure we don't notify the visible items change until after we've scrolled to the bottom on
  // bottom-up lists on mount. We do this by watching for range changes and ignoring them until the
  // user is at the correct start position (top for top-down, bottom for bottom-up).
  const handledFirstVisibleItemsRef = useRef(false);
  useLayoutEffect(() => {
    if (handledFirstVisibleItemsRef.current) return;

    if (direction !== 'bottom-up') {
      handledFirstVisibleItemsRef.current = true;
      return;
    }

    if (startIndex === null || endIndex === null) return;

    if (endIndex === totalItems - 1) {
      handledFirstVisibleItemsRef.current = true;
    }
  }, [direction, totalItems, startIndex, endIndex]);

  // Keep track of the last range we notified. This prevents duplicate notifs in the face of
  // unstable props such as the onVisibleItemsChange callback.
  const lastCheckedRangeRef = useRef<null | [number, number]>(null);

  // Notify whenever range changes.
  useEffect(() => {
    // Throw away the first visible range if we haven't handled scrolling to the bottom on
    // bottom-up feeds yet.
    if (!handledFirstVisibleItemsRef.current) return;

    // Bail if we have bad index data. This should never actually happen, but it's not worth a
    // fatal if it does.
    if (startIndex === null || endIndex === null) return;

    // If the range hasn't changed from last time we notified, bail.
    const [lastStartIndex, lastEndIndex] = lastCheckedRangeRef.current ?? [null, null];
    if (lastStartIndex === startIndex && lastEndIndex === endIndex) return;

    // Update the last notified range so we can reject future duplicates.
    lastCheckedRangeRef.current = [startIndex, endIndex];

    // Finally, notify the user of the new range.
    onVisibleItemsChange?.([startIndex, endIndex]);
  }, [startIndex, endIndex, onVisibleItemsChange]);
}

function usePinScrollToBottom({
  enabled,
  scrollContainer,
  contentContainer,
  onUserScroll,
  onContentResize,
  pinScrollToBottomRef,
}: {
  enabled: boolean;
  scrollContainer: HTMLDivElement | null;
  contentContainer: HTMLDivElement | null;
  onUserScroll: (scrollContainer: HTMLDivElement) => void;
  onContentResize?: () => void;
  pinScrollToBottomRef: React.RefObject<boolean>;
}) {
  // Keep track of the content height. If a scroll event happens and the content size has changed,
  // we assume the content changing size triggered the scroll event and we ignore the event.
  const lastContentOffsetHeightRef = useRef(0);

  // Add a resize listener to track if the content height changes.
  useLayoutEffect(() => {
    // Ensure the content and scroll containers are available. They always should, but we need to
    // narrow the nullable types.
    if (!contentContainer || !scrollContainer) return;

    const resizeObserver = new ResizeObserver(() => {
      // Record the new content height. This is necessary to reject onScroll events that happen as a
      // direct result to content size changes because the ordering of the events seems to be
      // reversed sometimes.
      lastContentOffsetHeightRef.current = contentContainer.offsetHeight;

      // Call the resize callback if provided
      onContentResize?.();

      // If we're not enabled, bail.
      if (!enabled) return;

      // If we're not supposed to pin to the bottom, there's no work to do. This would happen if the
      // user had previously scrolled away from the bottom.
      if (!pinScrollToBottomRef.current) return;

      // Okay, we need to pin to the bottom. Check if we're already there. This would happen if the
      // resize observer was triggered as a result of the content getting smaller.
      const actuallyAtBottom =
        scrollContainer.scrollTop + scrollContainer.offsetHeight >= scrollContainer.scrollHeight;

      // If we're already at the bottom, there's no work to do.
      if (actuallyAtBottom) return;

      // Finally, it's time to scroll to the bottom.
      scrollToBottom(scrollContainer);
    });

    resizeObserver.observe(contentContainer);
    resizeObserver.observe(scrollContainer);

    return () => {
      resizeObserver.disconnect();
    };
  }, [enabled, contentContainer, scrollContainer, onContentResize, pinScrollToBottomRef]);

  // Perpetually track if we're scrolled to the bottom.
  useLayoutEffect(() => {
    // Ensure the content and scroll containers are available. They always should, but we need to
    // narrow the nullable types.
    if (!scrollContainer) return;

    // Use a scroll listener to track changes. Inside, we'll reject changes that weren't
    // user-initiated.
    const onScroll = () => {
      // If the content container is not available, bail.
      if (!contentContainer) return;

      // Content size changes trigger scroll events. We distinguish these from user scroll events by
      // checking if the content size has changed. If it has, we bail here and we count on the
      // ResizeObserver to capture the event and handle it.
      if (lastContentOffsetHeightRef.current !== contentContainer.offsetHeight) return;

      // == At this point, we assume the scroll event was triggered by the user. == //

      // If we're at the bottom, we should pin the scroll bar through the next resize event.
      pinScrollToBottomRef.current =
        scrollContainer.scrollTop + scrollContainer.offsetHeight >=
        scrollContainer.scrollHeight - SCROLL_BOUNDARY_THRESHOLD;

      // Call the user's callback.
      onUserScroll?.(scrollContainer);
    };

    // Finally, register the scroll listener. We can use passive here because we're not going to
    // preventDefault.
    scrollContainer.addEventListener('scroll', onScroll, { passive: true });

    return () => {
      scrollContainer.removeEventListener('scroll', onScroll);
    };
  }, [scrollContainer, contentContainer, onUserScroll, pinScrollToBottomRef]);

  // Start by scrolling to the bottom for bottom-up lists.
  useLayoutEffect(() => {
    // Ensure the scroll container is available.
    if (!scrollContainer) return;

    // If we're not enabled, bail.
    if (!enabled) return;

    // Finally, scroll to the bottom.
    scrollToBottom(scrollContainer);

    // Now that we're at the bottom, stick there.
    pinScrollToBottomRef.current = true;
  }, [enabled, scrollContainer, pinScrollToBottomRef]);
}

/**
 * Force scroll to the absolute bottom of the container.
 */
function scrollToBottom(scrollContainer: HTMLDivElement) {
  scrollContainer.scrollTop = scrollContainer.scrollHeight;
}

/**
 * Each time the user scrolls, we want to notify the parent of the current "at top" and "at bottom"
 * states. We do this by listening to scroll events and checking the scroll position on scroll.
 *
 * Note that the scroll handler created in this hook isn't actually added to the scroll container.
 * This is because it's not as simple as adding an event listener, and we don't want to call it on
 * every single onScroll event; instead, we want to use this as the handler passed into
 * usePinScrollToBottom because that hook only calls the handler when the USER scrolls the container
 * (as opposed to resizes also triggering scroll events).
 */
function useScrolledBoundaryChanged(
  onScrolledBoundaryChanged?: (boundaries: { isAtTop: boolean; isAtBottom: boolean }) => void
): (scrollContainer: HTMLDivElement) => void {
  // Keep track of the last notified boundary to prevent duplicate notifications.
  const lastNotifiedBoundaryRef = useRef({
    isAtTop: true,
    isAtBottom: true,
  });

  // Create a scroll handler that calls the user's callback when the scroll boundary changes.
  const handleUserScroll = useCallback(
    (scrollContainer: HTMLDivElement) => {
      const isAtTop = scrollContainer.scrollTop <= SCROLL_BOUNDARY_THRESHOLD;
      const isAtBottom =
        scrollContainer.scrollTop + scrollContainer.offsetHeight >=
        scrollContainer.scrollHeight - SCROLL_BOUNDARY_THRESHOLD;

      // If the boundary state hasn't changed, bail.
      if (
        lastNotifiedBoundaryRef.current.isAtTop === isAtTop &&
        lastNotifiedBoundaryRef.current.isAtBottom === isAtBottom
      ) {
        return;
      }

      // Save the current boundary state.
      lastNotifiedBoundaryRef.current = { isAtTop, isAtBottom };

      // Notify the user.
      onScrolledBoundaryChanged?.({ isAtTop, isAtBottom });
    },
    [onScrolledBoundaryChanged]
  );

  return handleUserScroll;
}

/**
 * Scroll anchoring for paginated data. When items are inserted above the current viewport, this
 * hook maintains visual stability by adjusting the scroll position to keep the same content in
 * view.
 */
function useScrollAnchor({
  count,
  enabled,
  virtualizer,
  scrollContainer,
  direction,
}: {
  count: number;
  enabled: boolean;
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  scrollContainer: HTMLElement | null;
  direction: 'top-down' | 'bottom-up';
}) {
  const prevCountRef = useRef<number>(count);
  const prevAnchorRef = useRef<number | null>(null);
  const prevTotalSizeRef = useRef<number | null>(null);

  // When count changes, use previously captured state to adjust scroll position.
  useLayoutEffect(() => {
    if (!enabled || !scrollContainer) return;

    // If count changed and we have previous state, do adjustment.
    if (
      prevCountRef.current === count ||
      prevAnchorRef.current === null ||
      prevTotalSizeRef.current === null
    ) {
      return;
    }

    const currentTotalSize = virtualizer.getTotalSize();

    const capturedAnchor = prevAnchorRef.current;
    const capturedTotalSize = prevTotalSizeRef.current;

    // If totalSize also changed, do the adjustment.
    if (currentTotalSize !== capturedTotalSize) {
      const heightDelta = currentTotalSize - capturedTotalSize;
      const newScrollTop = doIt(() => {
        if (direction === 'bottom-up') {
          // For bottom-up: maintain distance from bottom.
          return scrollContainer.scrollHeight - capturedAnchor - scrollContainer.clientHeight;
        } else {
          // For top-down: maintain position from top.
          return capturedAnchor + heightDelta;
        }
      });

      scrollContainer.scrollTop = newScrollTop;
    }

    // Update previous count.
    prevCountRef.current = count;
  }, [count, enabled, virtualizer, scrollContainer, direction]);

  // Always capture current state for potential future use. This must be done after the scroll
  // anchoring effect above because it updates refs that scroll anchoring uses.
  useLayoutEffect(() => {
    if (!enabled || !scrollContainer) return;

    const currentTotalSize = virtualizer.getTotalSize();

    if (direction === 'bottom-up') {
      // For bottom-up, track distance from bottom.
      const distanceFromBottom =
        scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight;
      prevAnchorRef.current = distanceFromBottom;
    } else {
      // For top-down, track scroll position from top.
      prevAnchorRef.current = scrollContainer.scrollTop;
    }

    prevTotalSizeRef.current = currentTotalSize;
  });
}
