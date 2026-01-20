import React, { useId } from 'react';

import { Flex } from '../../layout/Flex/Flex';
import { Label } from '../Label/Label';
import { errorStyle, textAreaRecipe, TextAreaVariants } from './TextArea.css';

export type TextAreaProps = Omit<
  React.TextareaHTMLAttributes<HTMLTextAreaElement>,
  'className' | 'size'
> &
  Exclude<TextAreaVariants, 'hasError'> & {
    label?: string;
    required?: boolean;
    error?: string;
    id?: string;
    rows?: number;
    fullWidth?: boolean;
  };

export const TextArea = React.memo(
  React.forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
    { label, id: providedId, required, disabled, error, size, rows = 3, ...props },
    ref
  ) {
    const uniqueId = useId();
    const id = providedId ?? `TextArea-${uniqueId}`;
    const hasError = error != null && error !== '';
    const errorId = hasError ? `${id}-error` : undefined;

    return (
      <Flex gap={6} direction="column" flexGrow={1}>
        {label && (
          <Label size={size} htmlFor={id} required={required}>
            {label}
          </Label>
        )}
        <Flex direction="column" gap={2} flexGrow={1}>
          <textarea
            ref={ref}
            className={textAreaRecipe({ disabled, hasError, size })}
            id={id}
            required={required}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={errorId}
            rows={rows}
            {...props}
          />
          {hasError && (
            <span className={errorStyle} id={errorId}>
              {error}
            </span>
          )}
        </Flex>
      </Flex>
    );
  })
);
