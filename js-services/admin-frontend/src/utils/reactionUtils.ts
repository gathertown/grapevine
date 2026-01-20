import type { ThreadStat } from '../api/stats';

export type ReactionSentiment = 'positive' | 'negative' | 'neutral';

export interface ReactionInfo {
  counts: Record<string, number>;
  positiveCount: number;
  negativeCount: number;
  sentiment: ReactionSentiment;
}

export const normalizeReaction = (reaction: string): string => {
  return reaction.replace(/::skin-tone-[2-6]$/, '');
};

export const getReactionSentiment = (reaction: string): ReactionSentiment => {
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

export const getReactionEmoji = (reaction: string): string => {
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
};

export const getReactionCounts = (reactions: ThreadStat['reactions']): Record<string, number> => {
  return reactions.reduce<Record<string, number>>((acc, reaction) => {
    acc[reaction.reaction] = (acc[reaction.reaction] || 0) + 1;
    return acc;
  }, {});
};

export const getReactionInfo = (reactions: ThreadStat['reactions']): ReactionInfo => {
  const counts = getReactionCounts(reactions);

  const positiveCount = Object.entries(counts).reduce((sum, [reaction, count]) => {
    return getReactionSentiment(reaction) === 'positive' ? sum + count : sum;
  }, 0);

  const negativeCount = Object.entries(counts).reduce((sum, [reaction, count]) => {
    return getReactionSentiment(reaction) === 'negative' ? sum + count : sum;
  }, 0);

  const sentiment: ReactionSentiment =
    positiveCount > negativeCount
      ? 'positive'
      : negativeCount > positiveCount
        ? 'negative'
        : 'neutral';

  return {
    counts,
    positiveCount,
    negativeCount,
    sentiment,
  };
};
