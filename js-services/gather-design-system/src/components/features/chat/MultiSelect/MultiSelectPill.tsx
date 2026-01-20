import React from 'react';
import type { MultiValueProps } from 'react-select';

import { Uuid } from '../../../../utils/uuid';
import { IconButton } from '../../../base/IconButton/IconButton';
import { Text } from '../../../base/Text/Text';
import { pillContainerRecipe } from './MultiSelect.css';

export type MultiSelectPillProps<T extends { value: Uuid; label: string }> = Pick<
  MultiValueProps<T, true>,
  'data' | 'isFocused' | 'removeProps'
> & {
  InternalComponent?: React.ComponentType<{ data: T }>;
};

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const MultiSelectPill = React.memo(function MultiSelectPill<
  T extends { value: Uuid; label: string },
>({ data, isFocused, removeProps, InternalComponent }: MultiSelectPillProps<T>) {
  return (
    <div className={pillContainerRecipe({ selected: isFocused })}>
      {InternalComponent ? (
        <InternalComponent data={data} />
      ) : (
        <Text fontSize="sm">{data.label}</Text>
      )}
      <div onClick={removeProps.onClick}>
        <IconButton kind="transparent" icon="close" size="xs" />
      </div>
    </div>
  );
}) as <T extends { value: Uuid; label: string }>(
  props: MultiSelectPillProps<T>
) => React.ReactElement;
