import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadStat } from '../api/stats';
import { getChannelInfo, getReactionInfo, getFeedbackInfo } from '../utils';
import { useThreadExpansion } from '../hooks/useThreadExpansion';
import { useTextExpansion } from '../hooks/useTextExpansion';
import { ThreadHeader } from './ThreadHeader';
import { ThreadContent } from './ThreadContent';
import { ThreadFooter } from './ThreadFooter';
import { ThreadExpandedContent } from './ThreadExpandedContent';
import styles from './ThreadCard.module.css';

interface ThreadCardProps {
  thread: ThreadStat;
}

const ThreadCard: FC<ThreadCardProps> = memo(({ thread }) => {
  // Custom hooks for state management
  const threadExpansion = useThreadExpansion(thread.message_id);
  const textExpansion = useTextExpansion();

  // Computed values using utilities
  const channelInfo = getChannelInfo(thread.channel_id, thread.channel_name);
  const reactionInfo = getReactionInfo(thread.reactions);
  const feedbackInfo = getFeedbackInfo(thread.button_feedback || []);

  return (
    <div className={`${styles.threadCard} ${styles[reactionInfo.sentiment]}`}>
      <ThreadHeader
        thread={thread}
        channelInfo={channelInfo}
        reactionInfo={reactionInfo}
        feedbackInfo={feedbackInfo}
      />
      <ThreadContent thread={thread} channelInfo={channelInfo} textExpansion={textExpansion} />
      <ThreadFooter
        thread={thread}
        channelInfo={channelInfo}
        threadExpansion={threadExpansion}
        textExpansion={textExpansion}
      />
      <ThreadExpandedContent
        thread={thread}
        channelInfo={channelInfo}
        threadExpansion={threadExpansion}
        textExpansion={textExpansion}
      />
    </div>
  );
});

ThreadCard.displayName = 'ThreadCard';

export { ThreadCard };
