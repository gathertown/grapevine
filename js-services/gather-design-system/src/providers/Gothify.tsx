import React from 'react';

import { theme } from '@gathertown/gather-design-foundations';
import { colorMode } from './ThemeProvider.css';

// This component forces dark mode on its children, regardless of system/user preferences

type GothifyProps = React.PropsWithChildren & { enabled?: boolean };

export const Gothify = React.memo(
  React.forwardRef<HTMLDivElement, GothifyProps>(function Gothify(
    { children, enabled = false },
    ref
  ) {
    return (
      <div
        ref={ref}
        className={enabled ? colorMode['dark'] : ''}
        style={{
          display: 'contents',
          color: enabled ? theme.text.primary : 'initial',
        }}
      >
        {children}
      </div>
    );
  })
);
