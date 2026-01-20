import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadStat } from '../api/stats';
import type { ChannelInfo } from '../utils/threadUtils';
import type { UseTextExpansionReturn } from '../hooks/useTextExpansion';
import { truncateText } from '../utils/threadUtils';
import styles from './ThreadCard.module.css';

interface ThreadContentProps {
  thread: ThreadStat;
  channelInfo: ChannelInfo;
  textExpansion: UseTextExpansionReturn;
}

const ThreadContent: FC<ThreadContentProps> = memo(({ thread, channelInfo, textExpansion }) => {
  const { isTextExpanded } = textExpansion;

  return (
    <div className={styles.content}>
      <div className={styles.question}>
        <strong>Question:</strong>
        <p>{truncateText(thread.question)}</p>
      </div>

      <div className={styles.answer}>
        <strong>🤖 Bot Answer:</strong>
        <p>
          {channelInfo.type === 'dm' && isTextExpanded
            ? thread.answer
            : truncateText(thread.answer, 300)}
        </p>
      </div>
    </div>
  );
});

ThreadContent.displayName = 'ThreadContent';

export { ThreadContent };
