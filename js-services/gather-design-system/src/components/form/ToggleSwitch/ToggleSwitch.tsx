import React from 'react';

import { Text } from '../../base/Text/Text';
import { Flex } from '../../layout/Flex/Flex';
import {
  toggleFillRecipe,
  toggleInputStyle,
  toggleStyle,
  ToggleSwitchVariants,
} from './ToggleSwitch.css';

type Props = ToggleSwitchVariants & {
  name?: string;
  id?: string;
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  readOnly?: boolean;
  ariaLabel?: string;
  label?: string;
  hint?: string;
  dataTestId?: string;
};

export const ToggleSwitch = React.memo(
  React.forwardRef<HTMLInputElement, Props>(function ToggleSwitch(
    {
      id,
      name,
      size,
      checked,
      defaultChecked,
      onChange,
      ariaLabel,
      disabled,
      readOnly,
      label,
      hint,
      dataTestId,
    },
    ref
  ) {
    if (checked !== undefined && defaultChecked !== undefined) {
      throw new Error(
        "ToggleSwitch: Cannot use both 'checked' and 'defaultChecked' props simultaneously. Use 'checked' for controlled components or 'defaultChecked' for uncontrolled components."
      );
    }

    return (
      <label className={toggleStyle} htmlFor={id}>
        <input
          name={name}
          type="checkbox"
          id={id}
          checked={checked}
          defaultChecked={defaultChecked}
          onChange={onChange}
          className={toggleInputStyle}
          ref={ref}
          role="switch"
          disabled={disabled}
          // Ensure accessibility is not broken when using controlled
          aria-checked={checked !== undefined ? checked : undefined}
          aria-label={ariaLabel}
          readOnly={readOnly}
        />
        <div className={toggleFillRecipe({ size })} aria-hidden="true" data-testid={dataTestId} />
        {label && (
          <Flex direction="column" gap={2} mt={size === 'sm' ? -2 : 0}>
            <Text fontWeight="medium">{label}</Text>
            {hint && <Text color="tertiary">{hint}</Text>}
          </Flex>
        )}
      </label>
    );
  })
);
