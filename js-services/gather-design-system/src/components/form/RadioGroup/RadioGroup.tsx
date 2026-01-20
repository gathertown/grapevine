import React, { useCallback, useId, useState } from 'react';

import { Text } from '../../base/Text/Text';
import { Flex } from '../../layout/Flex/Flex';
import { Label } from '../Label/Label';
import { customRadioRecipe, inputStyle } from './RadioGroup.css';

type RadioGroupItemProps = {
  label: string;
  value: string;
  checked?: boolean;
  defaultChecked?: boolean;
  description?: string;
  disabled?: boolean;
  id?: string;
  isFocused?: boolean;
  name?: string;
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
  size?: RadioGroupBaseProps['size'];
};

type RadioGroupBaseProps = {
  name: string;
  items: Omit<RadioGroupItemProps, 'name'>[];
  label?: string;
  size?: 'xs' | 'sm' | 'md';
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
};

type RadioGroupControlledProps = RadioGroupBaseProps & {
  value: string;
  onChange: (value: string) => void;
  defaultValue?: never;
};

type RadioGroupUncontrolledProps = RadioGroupBaseProps & {
  value?: never;
  onChange?: never;
  defaultValue?: string;
};

type RadioGroupProps = RadioGroupControlledProps | RadioGroupUncontrolledProps;

export const RadioGroup = React.memo(function RadioGroup({
  defaultValue,
  items,
  label,
  name,
  onBlur,
  onChange,
  onFocus,
  size = 'md',
  value,
}: RadioGroupProps) {
  const isControlled = value !== undefined;
  const [internalValue, setInternalValue] = useState(defaultValue || '');
  const [focusedValue, setFocusedValue] = useState<string | null>(null);
  const currentValue = isControlled ? value : internalValue;

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      if (!isControlled) {
        setInternalValue(newValue);
      }
      onChange?.(newValue);
    },
    [isControlled, onChange]
  );
  const handleBlur = useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      setFocusedValue(null);
      onBlur?.(e);
    },
    [onBlur]
  );
  const handleFocus = useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      setFocusedValue(e.target.value);
      onFocus?.(e);
    },
    [onFocus]
  );

  return (
    <fieldset>
      <Flex direction="column" gap={4}>
        {label && (
          <legend>
            <Label>{label}</Label>
          </legend>
        )}
        <Flex direction="column" gap={8}>
          {items.map((item) => {
            const checked = item.value === currentValue;
            const isFocused = item.value === focusedValue;
            return (
              <RadioGroupItem
                key={item.value}
                {...item}
                checked={checked}
                name={name}
                onBlur={handleBlur}
                onChange={handleChange}
                onFocus={handleFocus}
                isFocused={isFocused}
                size={size}
              />
            );
          })}
        </Flex>
      </Flex>
    </fieldset>
  );
});

export const RadioGroupItem = React.memo(function RadioGroupItem({
  checked,
  defaultChecked,
  description,
  disabled,
  id: providedId,
  isFocused,
  label,
  name,
  onBlur,
  onChange,
  onFocus,
  size,
  value,
}: RadioGroupItemProps) {
  const uniqueId = useId();
  const id = providedId ?? `RadioGroupItem-${uniqueId}`;
  const descriptionId = description ? `description-${uniqueId}` : undefined;
  const gap = size === 'sm' ? 10 : 12;
  const fontSize = size === 'xs' ? 'sm' : 'md';

  return (
    <Flex direction="row" align="flex-start" gap={gap} position="relative">
      <div
        className={customRadioRecipe({ isChecked: checked, size, isDisabled: disabled, isFocused })}
      />
      <input
        aria-describedby={descriptionId}
        checked={checked}
        className={inputStyle}
        defaultChecked={defaultChecked}
        disabled={disabled}
        id={id}
        name={name}
        onBlur={onBlur}
        onChange={onChange}
        onFocus={onFocus}
        type="radio"
        value={value}
        data-testid={`radio-group-item-${value}`}
      />
      <Label htmlFor={id}>
        <Flex direction="column" gap={2}>
          <Text fontSize={fontSize}>{label}</Text>
          {description && (
            // TODO [DES-2723]: Support multiline <Text /> with better line height
            <div id={descriptionId} style={{ lineHeight: '1.25rem' }}>
              <Text fontSize={fontSize} fontWeight="normal" color="tertiary" lineHeight="inherit">
                {description}
              </Text>
            </div>
          )}
        </Flex>
      </Label>
    </Flex>
  );
});
