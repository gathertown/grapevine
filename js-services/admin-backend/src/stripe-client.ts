import { logger } from './utils/logger.js';
import Stripe from 'stripe';

let stripe: Stripe | null = null;
let hasTriedToInitializedStripe = false;

export const getOrInitializeStripe = (): Stripe | null => {
  if (stripe) {
    return stripe;
  }

  // We tried to initialize Stripe, but failed before...
  if (hasTriedToInitializedStripe) {
    logger.warn('Unable to get Stripe, prior initialization failed');
    return null;
  }

  hasTriedToInitializedStripe = true;
  const stripeSecretKey = process.env.STRIPE_SECRET_KEY;

  if (stripeSecretKey) {
    logger.info('Initializing Stripe');
    stripe = new Stripe(stripeSecretKey);
  } else {
    logger.warn('STRIPE_SECRET_KEY is not set; Stripe functionality will be disabled.');
  }

  return stripe;
};
