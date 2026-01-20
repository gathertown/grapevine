import type Stripe from 'stripe';

/**
 * Converts a Stripe timestamp (Unix seconds) to ISO string
 * @param timestamp - Stripe timestamp in seconds, or null
 * @returns ISO date string or null
 */
export function convertStripeTimestamp(timestamp: number | null): string | null {
  return timestamp ? new Date(timestamp * 1000).toISOString() : null;
}

/**
 * Extracts trial start and end dates from a Stripe subscription
 * @param subscription - Stripe subscription object
 * @returns Object with trialStart and trialEnd as ISO strings or null
 */
export function extractTrialDates(subscription: Stripe.Subscription) {
  return {
    trialStart: convertStripeTimestamp(subscription.trial_start),
    trialEnd: convertStripeTimestamp(subscription.trial_end),
  };
}
