import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadStat } from '../api/stats';
import type { ChannelInfo } from '../utils/threadUtils';
import type { UseThreadExpansionReturn } from '../hooks/useThreadExpansion';
import type { UseTextExpansionReturn } from '../hooks/useTextExpansion';
import { formatUserDisplay, needsExpansion } from '../utils/threadUtils';
import styles from './ThreadCard.module.css';

interface ThreadFooterProps {
  thread: ThreadStat;
  channelInfo: ChannelInfo;
  threadExpansion: UseThreadExpansionReturn;
  textExpansion: UseTextExpansionReturn;
}

const ThreadFooter: FC<ThreadFooterProps> = memo(
  ({ thread, channelInfo, threadExpansion, textExpansion }) => {
    const { isExpanded, isLoading, handleExpandToggle } = threadExpansion;
    const { isTextExpanded, handleTextExpandToggle } = textExpansion;

    const userDisplay = formatUserDisplay(
      thread.user_id,
      thread.user_name,
      thread.user_display_name
    );

    return (
      <div className={styles.footer}>
        <span className={styles.userId}>Asked by: {userDisplay}</span>
        {channelInfo.isChannel ? (
          <button className={styles.expandButton} onClick={handleExpandToggle} disabled={isLoading}>
            {isLoading ? (
              <>
                <div className={styles.spinner}></div>
                Loading...
              </>
            ) : (
              <>{isExpanded ? '▲ Hide Thread' : '▼ Show Thread'}</>
            )}
          </button>
        ) : (
          // Show expand button for DMs if answer text is long enough
          channelInfo.type === 'dm' &&
          needsExpansion(thread.answer, 300) && (
            <button className={styles.expandButton} onClick={handleTextExpandToggle}>
              {isTextExpanded ? '▲ Hide Full Answer' : '▼ Show Full Answer'}
            </button>
          )
        )}
      </div>
    );
  }
);

ThreadFooter.displayName = 'ThreadFooter';

export { ThreadFooter };
