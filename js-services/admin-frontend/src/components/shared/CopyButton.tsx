import { memo, useState, useCallback } from 'react';
import type { FC, ReactNode } from 'react';
import { Button } from '@gathertown/gather-design-system';

interface CopyButtonProps {
  textToCopy: string;
  children?: ReactNode;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onCopy?: () => void;
}

export const CopyButton: FC<CopyButtonProps> = memo(
  ({ textToCopy, children, size = 'sm', disabled = false, onCopy }) => {
    const [isCopied, setIsCopied] = useState(false);

    const handleCopy = useCallback(async () => {
      if (disabled || !textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        setIsCopied(true);
        onCopy?.();

        // Reset the "Copied!" state after 2 seconds
        setTimeout(() => {
          setIsCopied(false);
        }, 2000);
      } catch (error) {
        console.error('Failed to copy text:', error);
      }
    }, [textToCopy, disabled, onCopy]);

    return (
      <Button
        onClick={handleCopy}
        disabled={disabled}
        size={size}
        kind="primary"
        style={{
          fontSize: '12px',
          padding: '4px 8px',
          minWidth: '60px',
          // Green styling when copied
          ...(isCopied && {
            backgroundColor: '#28a745',
            color: 'white',
          }),
        }}
      >
        {children || (isCopied ? 'Copied!' : 'Copy')}
      </Button>
    );
  }
);

CopyButton.displayName = 'CopyButton';
