import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadStat } from '../api/stats';
import type { ChannelInfo } from '../utils/threadUtils';
import type { UseThreadExpansionReturn } from '../hooks/useThreadExpansion';
import type { UseTextExpansionReturn } from '../hooks/useTextExpansion';
import { ThreadDetailsComponent } from './ThreadDetails';
import styles from './ThreadCard.module.css';

interface ThreadExpandedContentProps {
  thread: ThreadStat;
  channelInfo: ChannelInfo;
  threadExpansion: UseThreadExpansionReturn;
  textExpansion: UseTextExpansionReturn;
}

const ThreadExpandedContent: FC<ThreadExpandedContentProps> = memo(
  ({ thread, channelInfo, threadExpansion, textExpansion }) => {
    const { isExpanded, threadDetails, error, handleExpandToggle } = threadExpansion;
    const { isTextExpanded } = textExpansion;

    const shouldShow =
      (isExpanded && channelInfo.isChannel) || (isTextExpanded && channelInfo.type === 'dm');

    if (!shouldShow) {
      return null;
    }

    return (
      <div className={styles.expandedContent}>
        {channelInfo.isChannel ? (
          // Show thread details for channels
          error ? (
            <div className={styles.error}>
              <p>Failed to load thread details: {error}</p>
              <button onClick={handleExpandToggle} className={styles.retryButton}>
                Retry
              </button>
            </div>
          ) : threadDetails ? (
            <ThreadDetailsComponent threadDetails={threadDetails} />
          ) : null
        ) : (
          // Show full text for DMs
          <div className={styles.fullTextContent}>
            <div className={styles.fullQuestion}>
              <strong>Question:</strong>
              <p>{thread.question}</p>
            </div>
            <div className={styles.fullAnswer}>
              <strong>🤖 Bot Answer:</strong>
              <p>{thread.answer}</p>
            </div>
          </div>
        )}
      </div>
    );
  }
);

ThreadExpandedContent.displayName = 'ThreadExpandedContent';

export { ThreadExpandedContent };
