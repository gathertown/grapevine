import React, { useId } from 'react';

import { isNotNilAndNotEmpty } from '../../../utils/fpHelpers';
import { GatherDesignSystemColors, theme } from '@gathertown/gather-design-foundations';
import { Icon, IconName } from '../../base/Icon/Icon';
import { Text } from '../../base/Text/Text';
import { Box } from '../../layout/Box/Box';
import { Flex } from '../../layout/Flex/Flex';
import { Label } from '../Label/Label';
import { iconRecipe, inputRecipe, InputVariants } from './Input.css';

type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'className' | 'size'> &
  Exclude<InputVariants, 'hasError'> & {
    label?: string;
    required?: boolean;
    error?: string;
    id?: string;
    fullWidth?: boolean;
    hint?: string;
    readOnly?: boolean;
    icon?: IconName;
    endIcon?: IconName;
    backgroundColor?: keyof GatherDesignSystemColors['bg'] | 'transparent';
  };

const iconSizeMap = {
  md: 'sm',
  lg: 'md',
} as const;

export const Input = React.memo(
  React.forwardRef<HTMLInputElement, InputProps>(function Input(
    {
      label,
      id: providedId,
      required,
      disabled,
      error,
      size = 'md',
      fullWidth,
      hint,
      readOnly,
      icon,
      endIcon,
      backgroundColor = 'primary',
      ...props
    },
    ref
  ) {
    const uniqueId = useId();
    const id = providedId ?? `Input-${uniqueId}`;
    const hintId = hint ? `${id}-hint` : undefined;
    const hasError = error != null && error !== '';
    const errorId = hasError ? `${id}-error` : undefined;
    const describedByIds = [hintId, errorId].filter(Boolean).join(' ') ?? undefined;
    const iconSize = iconSizeMap[size];

    return (
      <Flex gap={4} direction="column" width={fullWidth ? '100%' : undefined}>
        {label && (
          <Flex gap={2}>
            {readOnly && <Icon name="lockLocked" size="xs" color="tertiary" />}
            <Label size="md" htmlFor={id} required={required}>
              {label}
            </Label>
          </Flex>
        )}
        <Box position="relative" width="100%">
          <input
            ref={ref}
            className={inputRecipe({
              disabled,
              hasError,
              size,
              hasIcon: isNotNilAndNotEmpty(icon),
              hasEndIcon: isNotNilAndNotEmpty(endIcon),
            })}
            id={id}
            required={required}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={describedByIds}
            readOnly={readOnly}
            style={{
              backgroundColor:
                backgroundColor === 'transparent' ? 'transparent' : theme.bg[backgroundColor],
            }}
            {...props}
          />
          {icon && (
            <div className={iconRecipe({ isEnd: false })}>
              <Icon name={icon} size={iconSize} color="tertiary" />
            </div>
          )}
          {endIcon && (
            <div className={iconRecipe({ isEnd: true })}>
              <Icon name={endIcon} size={iconSize} color="tertiary" />
            </div>
          )}
        </Box>

        {hint && !hasError && (
          <Text fontSize="sm" color="tertiary" id={hintId}>
            {hint}
          </Text>
        )}
        {hasError && (
          <Text fontSize="sm" color="dangerPrimary" id={errorId}>
            {error}
          </Text>
        )}
      </Flex>
    );
  })
);
