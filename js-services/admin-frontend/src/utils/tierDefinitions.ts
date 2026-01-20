/**
 * Tier Definitions for UI Display
 *
 * This file contains the display text and feature definitions for each billing tier
 * to support internationalization and UI customization.
 */

export interface TierFeature {
  name: string;
  included: boolean;
  limit?: string;
}

export interface TierDefinition {
  name: string;
  description: string;
  price: string;
  period: string;
  features: TierFeature[];
  popular?: boolean;
}

export const tierDefinitions: Record<string, TierDefinition> = {
  basic: {
    name: 'Basic',
    description: 'Individuals and very small teams',
    price: '$150',
    period: '/mo',
    features: [
      { name: '200 questions/month', included: true, limit: '200' },
      { name: 'Slackbot integration', included: true },
      { name: 'Proactive responses', included: true },
    ],
  },
  team: {
    name: 'Team',
    description: 'Small teams, <15 users',
    price: '$300',
    period: '/mo',
    features: [
      { name: '500 questions/month', included: true, limit: '500' },
      { name: 'Slackbot integration', included: true },
      { name: 'Proactive responses', included: true },
    ],
  },
  pro: {
    name: 'Pro',
    description: 'Growing teams, up to 100 users',
    price: '$1,500',
    period: '/mo',
    features: [
      { name: '4,000 questions/month', included: true, limit: '4,000' },
      { name: 'Slackbot integration', included: true },
      { name: 'Proactive responses', included: true },
    ],
  },
  ultra: {
    name: 'Ultra',
    description: 'Large teams, up to 1000 users',
    price: '$5,000',
    period: '/mo',
    features: [
      { name: '15,000 questions/month', included: true, limit: '15,000' },
      { name: 'Slackbot integration', included: true },
      { name: 'Proactive responses', included: true },
      { name: 'Permission & RBAC support', included: true },
    ],
  },
  enterprise: {
    name: 'Enterprise',
    description: 'Very large organizations, unlimited users',
    price: 'Custom',
    period: '',
    features: [
      { name: 'Scale with unlimited questions', included: true },
      { name: 'Slackbot integration', included: true },
      { name: 'Proactive responses', included: true },
      { name: 'Permission & RBAC support', included: true },
      { name: 'Bring-your-own-key encryption', included: true },
    ],
  },
};

/**
 * Get tier definition by ID with fallback to basic info
 */
export function getTierDefinition(tierId: string): TierDefinition {
  return (
    tierDefinitions[tierId] || {
      name: tierId.charAt(0).toUpperCase() + tierId.slice(1),
      description: `${tierId} plan`,
      price: 'Custom',
      period: '',
      features: [],
    }
  );
}

/**
 * Get display name for a tier
 */
export function getTierName(tierId: string): string {
  return getTierDefinition(tierId).name;
}

/**
 * Get formatted price for a tier (price + period)
 */
export function getTierPrice(tierId: string): { price: string; period: string } {
  const tier = getTierDefinition(tierId);
  return {
    price: tier.price,
    period: tier.period,
  };
}
