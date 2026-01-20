import React, { ReactElement, useCallback, useId } from 'react';

import { isNotNilAndNotEmpty } from '../../../utils/fpHelpers';
import { Icon } from '../../base/Icon/Icon';
import { Text } from '../../base/Text/Text';
import { Box } from '../../layout/Box/Box';
import { Flex, FlexProps } from '../../layout/Flex/Flex';
import { Label } from '../Label/Label';
import { customCheckboxRecipe, inputStyle } from './Checkbox.css';

interface CheckboxProps {
  accentColor?: string;
  checked?: boolean;
  defaultChecked?: boolean;
  disabled?: boolean;
  error?: string;
  hint?: string;
  id?: string;
  align?: FlexProps['align'];
  labelLeadingElement?: ReactElement;
  label?: React.ReactNode;
  truncateLabel?: boolean;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onFocus?: (event: React.FocusEvent<HTMLInputElement>) => void;
  required?: boolean;
  size?: 'sm' | 'md';
}

const iconSizeMap = {
  sm: 'xs',
  md: 'sm',
} as const;

export const Checkbox = React.memo(
  React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
    {
      accentColor,
      checked,
      defaultChecked,
      disabled,
      error,
      hint,
      id: providedId,
      align = 'flex-start',
      labelLeadingElement,
      label,
      truncateLabel = false,
      onBlur,
      onChange,
      onFocus,
      required,
      size = 'md',
    },
    ref
  ) {
    const [isFocused, setIsFocused] = React.useState(false);
    const uniqueId = useId();
    const id = providedId ?? `Checkbox-${uniqueId}`;

    const hintId = isNotNilAndNotEmpty(hint) ? `${id}-hint` : undefined;
    const hasError = isNotNilAndNotEmpty(error);
    const errorId = hasError ? `${id}-error` : undefined;

    const [internalChecked, setInternalChecked] = React.useState(defaultChecked ?? false);
    const isControlled = checked !== undefined;
    const isChecked = isControlled ? checked : internalChecked;

    const handleChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!isControlled) {
          setInternalChecked(e.target.checked);
        }
        if (onChange) {
          onChange(e);
        }
      },
      [isControlled, onChange]
    );
    const handleFocus = useCallback(
      (e: React.FocusEvent<HTMLInputElement>) => {
        setIsFocused(true);
        if (onFocus) {
          onFocus(e);
        }
      },
      [onFocus]
    );
    const handleBlur = useCallback(
      (e: React.FocusEvent<HTMLInputElement>) => {
        setIsFocused(false);
        if (onBlur) {
          onBlur(e);
        }
      },
      [onBlur]
    );

    const iconColor = disabled ? 'primaryDisabled' : 'primaryOnDark';
    const customBackgroundColor = isChecked ? accentColor : undefined;
    const iconSize = iconSizeMap[size];
    const gap = size === 'sm' ? 10 : 12;

    return (
      <Flex direction="row" gap={gap} align={align} position="relative">
        <div
          className={customCheckboxRecipe({ isChecked, isDisabled: disabled, isFocused, size })}
          style={{ backgroundColor: customBackgroundColor, borderColor: customBackgroundColor }}
        >
          {isChecked && <Icon name="check" size={iconSize} color={iconColor} />}
        </div>
        <input
          aria-describedby={errorId}
          aria-invalid={hasError}
          checked={checked}
          className={inputStyle}
          defaultChecked={defaultChecked}
          disabled={disabled}
          id={id}
          onBlur={handleBlur}
          onChange={handleChange}
          onFocus={handleFocus}
          ref={ref}
          required={required}
          type="checkbox"
          data-testid={`${label}-checkbox`}
        />
        <Flex direction="column" gap={2}>
          {label && (
            <>
              <Label htmlFor={id} required={required} hasCursor>
                <Flex gap={labelLeadingElement ? gap : 0} align={align}>
                  {labelLeadingElement}
                  <Text fontWeight="medium" truncate={truncateLabel}>
                    {label}
                  </Text>
                </Flex>
              </Label>
              {hint && !hasError && (
                <Box pl={0}>
                  <Text id={hintId} color="tertiary">
                    {hint}
                  </Text>
                </Box>
              )}
              {hasError && (
                <Box pl={0}>
                  <Text id={errorId} color="dangerPrimary">
                    {error}
                  </Text>
                </Box>
              )}
            </>
          )}
        </Flex>
      </Flex>
    );
  })
);
