import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Text } from '../Text/Text';
import { highlightBar, segmentedControlWrapper, segmentStyle } from './SegmentedControl.css';

type Segment = {
  label: string;
  value: string;
};

export type SegmentedControlProps = {
  segments: Segment[];
  defaultValue?: string;
  onSegmentChange: (value: string) => void;
};

export const SegmentedControl = React.memo<SegmentedControlProps>(function SegmentedControl({
  onSegmentChange,
  segments,
  defaultValue,
}) {
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [selectedSegment, setSelectedSegment] = useState<string | undefined>(
    defaultValue ?? segments[0]?.value
  );

  const [highlightStyle, setHighlightStyle] = useState({ width: 0, left: 0 });

  const selectedIndex = useMemo(
    () => segments.findIndex((s) => s.value === selectedSegment),
    [segments, selectedSegment]
  );

  const updateHighlightPosition = useCallback(() => {
    if (selectedIndex < 0) return;

    const button = buttonRefs.current[selectedIndex];
    if (!button || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();

    setHighlightStyle({
      width: buttonRect.width,
      left: buttonRect.left - containerRect.left,
    });
  }, [selectedIndex]);

  useEffect(() => {
    updateHighlightPosition();
  }, [updateHighlightPosition]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver(() => {
      updateHighlightPosition();
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
    };
  }, [updateHighlightPosition]);

  const handleSegmentChange = (value: string) => {
    setSelectedSegment(value);
    onSegmentChange(value);
  };

  const setButtonRef = useCallback((element: HTMLButtonElement | null, index: number) => {
    buttonRefs.current[index] = element;
  }, []);

  return (
    <div className={segmentedControlWrapper} ref={containerRef}>
      <div
        className={highlightBar}
        style={{
          width: highlightStyle.width,
          transform: `translateX(${highlightStyle.left}px)`,
        }}
      />

      {segments.map((segment, index) => {
        const isActive = selectedSegment === segment.value;
        return (
          <button
            key={segment.value}
            className={segmentStyle}
            ref={(el) => setButtonRef(el, index)}
            onClick={() => handleSegmentChange(segment.value)}
          >
            <Text
              as="p"
              fontWeight="medium"
              fontSize="xxs"
              color={isActive ? 'primary' : 'secondary'}
            >
              {segment.label}
            </Text>
          </button>
        );
      })}
    </div>
  );
});
