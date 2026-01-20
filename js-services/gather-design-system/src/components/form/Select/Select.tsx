import * as SelectPrimitive from '@radix-ui/react-select';
import React from 'react';

import { isNotEmpty, isNotNil } from '../../../utils/fpHelpers';
import { GatherDesignSystemColors, theme } from '@gathertown/gather-design-foundations';
import { usePortalContainer } from '../../../helpers/usePortalContainer';
import { Icon } from '../../base/Icon/Icon';
import { Flex } from '../../layout/Flex/Flex';
import { Label } from '../Label/Label';
import {
  contentStyle,
  errorStyle,
  itemStyle,
  selectTriggerRecipe,
  viewportStyle,
} from './Select.css';

export interface SelectOption {
  label: string;
  value: string;
}

export interface SelectProps {
  label?: string;
  required?: boolean;
  error?: string;
  id?: string;
  options: SelectOption[];
  placeholder?: string;
  value?: string;
  disabled?: boolean;
  onChange?: (value: string) => void;
  portalContainerId?: string;
  backgroundColor?: keyof GatherDesignSystemColors['bg'] | 'transparent';
  renderOption?: (option: SelectOption) => React.ReactNode;
}

export const Select = React.memo(
  React.forwardRef<HTMLButtonElement, SelectProps>(function Select(
    {
      label,
      id: providedId,
      required,
      disabled,
      error,
      options,
      placeholder,
      value,
      onChange,
      portalContainerId,
      backgroundColor = 'primary',
      renderOption,
    },
    ref
  ) {
    const uniqueId = React.useId();
    const id = providedId ?? `Select-${uniqueId}`;
    const hasError = isNotNil(error) && isNotEmpty(error);
    const errorId = hasError ? `${id}-error` : undefined;
    const container = usePortalContainer(portalContainerId);
    const selectedOption = options.find((option) => option.value === value);

    if (renderOption && !onChange) {
      throw new Error(
        'Select component with renderOption must be controlled. Please provide an onChange handler and a value.'
      );
    }

    const shouldUseCustomRenderOption = renderOption && selectedOption;

    return (
      <Flex gap={6} direction="column">
        {label && (
          <Label htmlFor={id} required={required}>
            {label}
          </Label>
        )}
        <Flex gap={2} direction="column">
          <SelectPrimitive.Root
            // Radix UI Select doesn't handle undefined values properly - when value is undefined,
            // the component can get stuck and won't show placeholder or allow new selections.
            // Using empty string ensures proper reset behavior when clearing the selection.
            value={value ?? ''}
            onValueChange={onChange}
            required={required}
            disabled={disabled}
          >
            <SelectPrimitive.Trigger
              ref={ref}
              id={id}
              className={selectTriggerRecipe({ disabled, error: hasError })}
              aria-invalid={hasError}
              aria-describedby={errorId}
              disabled={disabled}
              style={{
                backgroundColor:
                  backgroundColor === 'transparent' ? 'transparent' : theme.bg[backgroundColor],
              }}
            >
              {shouldUseCustomRenderOption ? (
                <SelectPrimitive.Value placeholder={placeholder} asChild>
                  {renderOption(selectedOption)}
                </SelectPrimitive.Value>
              ) : (
                <SelectPrimitive.Value placeholder={placeholder} />
              )}

              <SelectPrimitive.Icon>
                <Icon name="chevronDown" size="xs" color="tertiary" />
              </SelectPrimitive.Icon>
            </SelectPrimitive.Trigger>

            <SelectPrimitive.Portal container={container}>
              <SelectPrimitive.Content className={contentStyle} position="popper" sideOffset={4}>
                <SelectPrimitive.Viewport className={viewportStyle}>
                  {options.map((option) => (
                    <SelectPrimitive.Item
                      className={itemStyle}
                      key={option.value}
                      value={option.value}
                    >
                      {renderOption ? (
                        renderOption(option)
                      ) : (
                        <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                      )}
                      <SelectPrimitive.ItemIndicator>
                        <Icon name="check" size="xs" color="primary" />
                      </SelectPrimitive.ItemIndicator>
                    </SelectPrimitive.Item>
                  ))}
                </SelectPrimitive.Viewport>
              </SelectPrimitive.Content>
            </SelectPrimitive.Portal>
          </SelectPrimitive.Root>
          {hasError && (
            <div id={errorId} className={errorStyle}>
              {error}
            </div>
          )}
        </Flex>
      </Flex>
    );
  })
);
