import type { SubscriptionStatus } from '../types';

/**
 * Gets the effective end date for a subscription, prioritizing trial end date
 * if the subscription is in trialing status, otherwise using currentPeriodEnd.
 * This handles the case where cancelled trial subscriptions should show the trial
 * end date instead of the extended subscription period end date.
 */
export function getEffectiveEndDate(subscription: SubscriptionStatus): string | null {
  if (subscription.status === 'trialing' && subscription.trialEnd) {
    return subscription.trialEnd;
  }
  return subscription.currentPeriodEnd;
}

/**
 * Formats a date string into a user-friendly format (Month Day, Year)
 */
export function formatEndDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}
