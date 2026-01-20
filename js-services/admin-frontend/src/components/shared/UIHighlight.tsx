import type { FC, ReactNode } from 'react';

interface UIHighlightProps {
  children: ReactNode;
  variant?: 'default' | 'code';
}

/**
 * Shared component for highlighting UI elements consistently across the app.
 * Uses yellow highlight styling to make UI elements stand out in instructions.
 */
export const UIHighlight: FC<UIHighlightProps> = ({ children, variant = 'default' }) => {
  const baseStyle = {
    backgroundColor: '#fef3c7',
    color: '#92400e',
    padding: '2px 4px',
    borderRadius: '4px',
    fontWeight: 'medium' as const,
    fontFamily:
      'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace',
    fontSize: variant === 'code' ? '0.9em' : 'inherit',
    display: 'inline-block',
  };

  return <span style={baseStyle}>{children}</span>;
};
