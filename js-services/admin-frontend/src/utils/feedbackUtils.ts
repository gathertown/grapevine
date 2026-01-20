import type { SlackFeedback } from '../api/stats';

export type FeedbackSentiment = 'positive' | 'negative' | 'mixed' | 'none';

export interface FeedbackInfo {
  positive: number;
  negative: number;
  total: number;
  sentiment: FeedbackSentiment;
}

export const getFeedbackInfo = (feedback: SlackFeedback[]): FeedbackInfo => {
  const positive = feedback.filter((f) => f.feedback_type === 'positive').length;
  const negative = feedback.filter((f) => f.feedback_type === 'negative').length;
  const total = feedback.length;

  let sentiment: FeedbackSentiment;
  if (total === 0) {
    sentiment = 'none';
  } else if (positive > negative) {
    sentiment = 'positive';
  } else if (negative > positive) {
    sentiment = 'negative';
  } else {
    sentiment = 'mixed';
  }

  return { positive, negative, total, sentiment };
};
