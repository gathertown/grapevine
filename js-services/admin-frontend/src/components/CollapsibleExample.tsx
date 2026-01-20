import { useState, memo } from 'react';
import type { FC, ReactNode } from 'react';
import styles from './CollapsibleExample.module.css';

interface CollapsibleExampleProps {
  title?: string;
  children: ReactNode;
}

const CollapsibleExample: FC<CollapsibleExampleProps> = memo(
  ({ title = 'View Example', children }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const toggleExpanded = () => {
      setIsExpanded((prev) => !prev);
    };

    return (
      <div className={styles.collapsibleExample}>
        <button
          type="button"
          className={styles.toggleButton}
          onClick={toggleExpanded}
          aria-expanded={isExpanded}
        >
          <span className={styles.toggleIcon}>{isExpanded ? '▼' : '▶'}</span>
          <span
            style={{
              lineClamp: 2,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {isExpanded ? 'Hide Example' : title}
          </span>
        </button>

        {isExpanded && <div className={styles.exampleContent}>{children}</div>}
      </div>
    );
  }
);

CollapsibleExample.displayName = 'CollapsibleExample';

export { CollapsibleExample };
