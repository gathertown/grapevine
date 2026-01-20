import { memo } from 'react';
import type { FC } from 'react';
import type { ThreadDetails, ThreadMessage } from '../api/stats';
import styles from './ThreadDetails.module.css';

interface ThreadDetailsProps {
  threadDetails: ThreadDetails;
}

const ThreadDetailsComponent: FC<ThreadDetailsProps> = memo(({ threadDetails }) => {
  // Helper function to normalize skin tone reactions for counting
  const normalizeReaction = (reaction: string): string => {
    return reaction.replace(/::skin-tone-[2-6]$/, '');
  };

  // Helper function to determine reaction sentiment
  const getReactionSentiment = (reaction: string): 'positive' | 'negative' | 'neutral' => {
    const normalized = normalizeReaction(reaction);
    const positiveReactions = [
      '+1',
      'thumbsup',
      'fire',
      'heavy_check_mark',
      'clap',
      'heart',
      'star',
      'pray',
      'thankyou',
    ];
    const negativeReactions = ['-1', 'thumbsdown', 'x', 'confused', 'thinking_face'];

    if (positiveReactions.includes(normalized)) return 'positive';
    if (negativeReactions.includes(normalized)) return 'negative';
    return 'neutral';
  };

  // Format message timestamp
  const formatTimestamp = (timestamp: string): string => {
    const ts = parseFloat(timestamp);
    const date = new Date(ts * 1000);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Render message reactions
  const renderReactions = (message: ThreadMessage) => {
    if (message.reactions.length === 0) return null;

    // Group reactions by type and count them
    const reactionCounts: Record<string, number> = message.reactions.reduce<Record<string, number>>(
      (acc, reaction) => {
        acc[reaction.reaction] = (acc[reaction.reaction] || 0) + 1;
        return acc;
      },
      {}
    );

    return (
      <div className={styles.messageReactions}>
        {Object.entries(reactionCounts).map(([reaction, count]) => (
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
            {(() => {
              const normalized = normalizeReaction(reaction);
              const emojiMap: Record<string, string> = {
                '+1': '👍',
                thumbsup: '👍',
                '-1': '👎',
                thumbsdown: '👎',
                fire: '🔥',
                heavy_check_mark: '✅',
                clap: '👏',
                heart: '❤️',
                star: '⭐',
                pray: '🙏',
                thankyou: '🙏',
                x: '❌',
                confused: '😕',
                thinking_face: '🤔',
              };
              return emojiMap[normalized] || reaction;
            })()}{' '}
            {count}
          </span>
        ))}
      </div>
    );
  };

  // Format message text (handle basic markdown)
  const formatMessageText = (text: string): string => {
    if (!text) return '';

    // Replace user mentions
    return text
      .replace(/<@(\w+)>/g, '@$1')
      .replace(/<#(\w+)\|([^>]+)>/g, '#$2')
      .replace(/<([^>]+)>/g, '$1');
  };

  // Format user display name
  const formatUserDisplay = (
    userId: string,
    userName?: string,
    userDisplayName?: string
  ): string => {
    // Prefer display name, then username, then user ID
    if (userDisplayName) {
      return userDisplayName;
    }
    if (userName) {
      return `@${userName}`;
    }
    return userId;
  };

  return (
    <div className={styles.threadDetails}>
      <div className={styles.threadHeader}>
        <h4>Full Thread Context</h4>
        <span className={styles.threadInfo}>
          #{threadDetails.channel_id} • {threadDetails.messages.length} messages
        </span>
      </div>

      <div className={styles.timeline}>
        {threadDetails.messages.map((message, index) => (
          <div
            key={message.message_id}
            className={`${styles.message} ${message.is_bot ? styles.botMessage : styles.userMessage}`}
          >
            <div className={styles.messageHeader}>
              <span className={styles.messageAuthor}>
                {message.is_bot
                  ? '🤖 Bot'
                  : `👤 ${formatUserDisplay(message.user_id, message.user_name, message.user_display_name)}`}
              </span>
              <span className={styles.messageTime}>{formatTimestamp(message.timestamp)}</span>
              {message.message_id === threadDetails.original_question_message_id && (
                <span className={styles.messageLabel}>Original Question</span>
              )}
              {message.message_id === threadDetails.bot_response_message_id && (
                <span className={styles.messageLabel}>Bot Response</span>
              )}
            </div>

            <div className={styles.messageContent}>
              <p>{formatMessageText(message.text)}</p>
            </div>

            {renderReactions(message)}

            {index < threadDetails.messages.length - 1 && (
              <div className={styles.timelineConnector}></div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
});

ThreadDetailsComponent.displayName = 'ThreadDetailsComponent';

export { ThreadDetailsComponent };
