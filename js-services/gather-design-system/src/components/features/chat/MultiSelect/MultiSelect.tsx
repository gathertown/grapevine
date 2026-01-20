import React, { useEffect, useRef, useState } from 'react';
import Select, { FilterOptionOption, GroupBase, MultiValue, SelectInstance } from 'react-select';

import { Uuid } from '../../../../utils/uuid';
import { theme, tokens } from '@gathertown/gather-design-foundations';
import { MultiSelectDropdownProps, MultiSelectDropdownRow } from './MultiSelectDropdownRow';
import { MultiSelectPill, MultiSelectPillProps } from './MultiSelectPill';

type Props<Option extends { value: Uuid; label: string }> = {
  options: Option[];
  PillInternalComponent?: React.ComponentType<Pick<MultiSelectPillProps<Option>, 'data'>>;
  DropdownRowInternalComponent?: React.ComponentType<
    Pick<MultiSelectDropdownProps<Option>, 'data'>
  >;
  bordered?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  defaultMenuIsOpen?: boolean;
  handleEnter?: () => void;
  values: MultiValue<Option> | undefined;
  // callback that returns the entirety of the selected options. THis is for managing the controlled form of the component
  handleChange: (values: MultiValue<Option>) => void;
  // callback that returns just the values from the selected options
  handleValuesChange?: (values: Uuid[]) => void;

  filterOption?: (option: FilterOptionOption<Option>, inputValue: string) => boolean;
  inputId?: string;
};

export type {
  MultiSelectDropdownProps as DefaultDropdownRowProps,
  MultiSelectPillProps as DefaultPillProps,
};

const INPUT_HEIGHT = 44;

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
const MultiSelectControlled = React.memo(function MultiSelectControlled<T>({
  options,
  PillInternalComponent,
  DropdownRowInternalComponent,
  bordered = true,
  handleChange,
  placeholder,
  autoFocus = false,
  defaultMenuIsOpen = false,
  handleEnter,
  values,
  handleValuesChange,
  filterOption,
  inputId,
}: Props<T & { value: Uuid; label: string }>) {
  const ref =
    useRef<
      SelectInstance<
        T & { value: Uuid; label: string },
        true,
        GroupBase<T & { value: Uuid; label: string }>
      >
    >(null);

  const [isOpen, setIsOpen] = useState(defaultMenuIsOpen);
  const onChange = (selectedOptions: MultiValue<T & { value: Uuid; label: string }>) => {
    setIsOpen(false);
    handleChange(selectedOptions);
    handleValuesChange?.(selectedOptions.map((option) => option.value));
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    // pressing enter on the multi select input while the dropdown is open should close the dropdown
    if (event.key === 'Enter' && isOpen) {
      setIsOpen(false);
      // pressing enter on the multi select input while dropdown is open should call handleEnter callback
    } else if (event.key === 'Enter') {
      handleEnter?.();
      // any other key opens the dropdown
    } else {
      setIsOpen(true);
    }
  };

  // Delay focus until the next animation frame so the input is fully mounted and painted.
  // This is important because:
  // 1. React's useEffect runs before the browser paints, so focus might fail if the element isn't visible yet.
  // 2. If this input is inside a modal (e.g. Radix Dialog), the dialog's focus trap might still be running
  //    and could steal focus back immediately.
  // requestAnimationFrame ensures we apply focus *after* layout, paint, and any focus-trap logic.
  useEffect(() => {
    let rafId: number;

    if (autoFocus) {
      rafId = requestAnimationFrame(() => {
        ref.current?.focus();
      });
    }

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [autoFocus]);

  return (
    <Select
      inputId={inputId}
      onBlur={() => setIsOpen(false)}
      onFocus={() => {
        if (values && values.length === 0) {
          setIsOpen(true);
        }
      }}
      onKeyDown={handleKeyDown}
      menuIsOpen={isOpen}
      isMulti
      autoFocus={autoFocus}
      placeholder={placeholder}
      value={values}
      styles={{
        // These control the input and dropdown container styling. They would require more work to replace the entire component so just
        // overriding the styles here
        control: (base) =>
          bordered
            ? {
                ...base,
                borderRadius: tokens.borderRadius[12],
                minHeight: INPUT_HEIGHT,
                color: theme.text.primary,
                backgroundColor: theme.bg.mainContent,
              }
            : {
                ...base,
                border: 'none', // 👈 Removes the outer border
                boxShadow: 'none', // 👈 Removes the focus ring
                color: theme.text.primary,
                backgroundColor: theme.bg.mainContent,
                minHeight: INPUT_HEIGHT,
              },

        menuList: (base) => ({
          ...base,
          padding: tokens.scale[8],
          boxShadow: tokens.boxShadow.md,
        }),
        menu: (base) => ({
          ...base,
          backgroundColor: theme.bg.primary,
          border: `1px solid ${theme.border.tertiary}`,
        }),
        placeholder: (base) => ({
          ...base,
          color: theme.text.tertiary,
          fontSize: tokens.fontSize.sm,
          fontWeight: tokens.fontWeight.medium,
        }),
        noOptionsMessage: (base) => ({
          ...base,
          fontSize: tokens.fontSize.sm,
        }),
        container: (base) => ({
          ...base,
          width: '100%',
        }),
        input: (base) => ({
          ...base,
          fontSize: tokens.fontSize.md,
          color: theme.text.primary,
        }),
      }}
      onChange={onChange}
      options={options}
      components={{
        MultiValue: (props) => (
          <MultiSelectPill<T & { value: Uuid; label: string }>
            {...props}
            InternalComponent={PillInternalComponent}
          />
        ),
        Option: (props) => (
          <MultiSelectDropdownRow<T & { value: Uuid; label: string }>
            innerRef={props.innerRef}
            data={props.data}
            innerProps={props.innerProps}
            isFocused={props.isFocused}
            InternalComponent={DropdownRowInternalComponent}
          />
        ),
        DropdownIndicator: () => null,
        ClearIndicator: () => null,
        IndicatorSeparator: () => null,
      }}
      ref={ref}
      filterOption={filterOption}
    />
  );
}) as <T>(props: Props<T & { value: Uuid; label: string }>) => React.ReactElement;

type MultiSelectWrapperProps<T> = Omit<
  Props<T & { value: Uuid; label: string }>,
  'handleChange' | 'values'
>;

const MultiSelectWrapper = React.memo(function MultiSelectWrapper<
  Option extends { value: Uuid; label: string } = { value: Uuid; label: string },
>(props: MultiSelectWrapperProps<Option>) {
  const [values, setValues] = useState<MultiValue<Option> | undefined>();

  return <MultiSelectControlled {...props} values={values} handleChange={setValues} />;
});

export const MultiSelect = Object.assign(MultiSelectWrapper, {
  Controlled: MultiSelectControlled,
});
