import * as SliderPrimitive from '@radix-ui/react-slider';
import { head } from 'ramda';
import React from 'react';

import { isNil } from '../../../utils/fpHelpers';
import {
  sliderRangeStyle,
  sliderRootStyle,
  sliderThumbStyle,
  sliderTrackStyle,
} from './Slider.css';

export type SliderProps = {
  id?: string;
  min?: number;
  max?: number;
  defaultValue?: number;
  value?: number;
  onValueChange?: (value: number) => void;
  onValueCommit?: (value: number) => void;
  orientation?: 'horizontal' | 'vertical';
  isDisabled?: boolean;
  step?: number;
};

export const Slider = React.memo(
  React.forwardRef<HTMLDivElement, SliderProps>(function Slider(
    {
      id,
      min = 0,
      max = 100,
      orientation = 'horizontal',
      isDisabled = false,
      step = 1,
      defaultValue,
      value,
      onValueChange,
      onValueCommit,
    },
    ref
  ) {
    // Convert single value to array for Radix UI Slider
    const valueArray = isNil(value) ? undefined : [value];
    const defaultValueArray = isNil(defaultValue) ? undefined : [defaultValue];

    // Handle value change from array to single number
    const handleValueChange = onValueChange
      ? (values: number[]) => {
          const val = head(values);
          if (val === undefined) throw new Error('Slider value is undefined');
          onValueChange(val);
        }
      : undefined;

    const handleValueCommit = onValueCommit
      ? (values: number[]) => {
          const val = head(values);
          if (val === undefined) throw new Error('Slider value is undefined');
          onValueCommit(val);
        }
      : undefined;

    return (
      <SliderPrimitive.Root
        id={id}
        ref={ref}
        className={sliderRootStyle({ orientation })}
        min={min}
        max={max}
        value={valueArray}
        defaultValue={defaultValueArray}
        onValueChange={handleValueChange}
        onValueCommit={handleValueCommit}
        orientation={orientation}
        disabled={isDisabled}
        step={step}
      >
        <SliderPrimitive.Track className={sliderTrackStyle({ orientation })}>
          <SliderPrimitive.Range className={sliderRangeStyle({ orientation })} />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className={sliderThumbStyle({ disabled: isDisabled })} />
      </SliderPrimitive.Root>
    );
  })
);
