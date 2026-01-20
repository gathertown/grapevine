import type { FC, ReactNode } from 'react';

interface NavigationHighlightProps {
  children: ReactNode;
}

const NavigationHighlight: FC<NavigationHighlightProps> = ({ children }) => {
  return (
    <span
      style={{
        backgroundColor: '#fef3c7',
        color: '#92400e',
        padding: '2px 4px',
        borderRadius: '4px',
        fontWeight: 'medium',
        fontFamily:
          'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace',
      }}
    >
      {children}
    </span>
  );
};

export { NavigationHighlight };
