import React from 'react';
import type { GroupBase, OptionProps } from 'react-select';

import { Uuid } from '../../../../utils/uuid';
import { Text } from '../../../base/Text/Text';
import { dropdownRowContainerRecipe } from './MultiSelect.css';

export type MultiSelectDropdownProps<T extends { value: Uuid; label: string }> = Pick<
  OptionProps<T, true, GroupBase<T>>,
  'isFocused' | 'innerProps' | 'data'
> & {
  InternalComponent?: React.ComponentType<{ data: T }>;
  innerRef?: React.Ref<HTMLDivElement>;
};

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const MultiSelectDropdownRow = React.memo(function MultiSelectDropdownRow<
  T extends { value: Uuid; label: string },
>({ data, isFocused, innerProps, InternalComponent, innerRef }: MultiSelectDropdownProps<T>) {
  return (
    <div
      ref={innerRef}
      className={dropdownRowContainerRecipe({
        highlighted: isFocused,
      })}
      {...innerProps}
      data-testid={`multi-select-dropdown-row-${data.label}`}
    >
      {InternalComponent ? (
        <InternalComponent data={data} />
      ) : (
        <Text fontSize="sm">{data.label}</Text>
      )}
    </div>
  );
}) as <T extends { value: Uuid; label: string }>(
  props: MultiSelectDropdownProps<T>
) => React.ReactElement;
