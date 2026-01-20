import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadStat } from '../api/stats';
import type { ChannelInfo } from '../utils/threadUtils';
import type { ReactionInfo } from '../utils/reactionUtils';
import type { FeedbackInfo } from '../utils/feedbackUtils';
import { formatDate } from '../utils/threadUtils';
import { getReactionSentiment, getReactionEmoji } from '../utils/reactionUtils';
import styles from './ThreadCard.module.css';

interface ThreadHeaderProps {
  thread: ThreadStat;
  channelInfo: ChannelInfo;
  reactionInfo: ReactionInfo;
  feedbackInfo: FeedbackInfo;
}

const ThreadHeader: FC<ThreadHeaderProps> = memo(
  ({ thread, channelInfo, reactionInfo, feedbackInfo }) => {
    const formattedDate = formatDate(thread.created_at);

    return (
      <div className={styles.header}>
        <div className={styles.metadata}>
          <span
            className={`${styles.channel} ${channelInfo.type === 'dm' ? styles.dmChannel : ''}`}
          >
            {channelInfo.display}
          </span>
          {thread.is_proactive && (
            <span className={styles.proactiveBadge} title="Proactive response">
              Proactive
            </span>
          )}
          <span className={styles.date}>{formattedDate}</span>
        </div>
        {feedbackInfo.total > 0 && (
          <div className={styles.feedback}>
            {feedbackInfo.positive > 0 && (
              <span className={`${styles.feedbackButton} ${styles.positive}`}>
                👍 {feedbackInfo.positive}
              </span>
            )}
            {feedbackInfo.negative > 0 && (
              <span className={`${styles.feedbackButton} ${styles.negative}`}>
                👎 {feedbackInfo.negative}
              </span>
            )}
          </div>
        )}
        {thread.reactions.length > 0 && (
          <div className={styles.reactions}>
            {Object.entries(reactionInfo.counts).map(([reaction, count]) => (
              <span
                key={reaction}
                className={`${styles.reaction} ${
                  getReactionSentiment(reaction) === 'positive'
                    ? styles.positive
                    : getReactionSentiment(reaction) === 'negative'
                      ? styles.negative
                      : ''
                }`}
              >
                {getReactionEmoji(reaction)} {count}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }
);

ThreadHeader.displayName = 'ThreadHeader';

export { ThreadHeader };
