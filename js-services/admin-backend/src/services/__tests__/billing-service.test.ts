/**
 * Tests for billing service functions, specifically trial period logic
 */

import {
  calculateTrialStatus,
  calculateRemainingTrialEnd,
  isBillingRequired,
} from '../billing-service';
import { SubscriptionRecord } from '../../dal/subscriptions';

// Test data factories to avoid duplication
const createMockSubscription = (
  overrides: Partial<SubscriptionRecord> = {}
): SubscriptionRecord => ({
  id: 'test-id',
  tenant_id: 'test-tenant',
  stripe_customer_id: 'cus_test',
  stripe_subscription_id: 'sub_test',
  stripe_product_id: 'prod_test',
  stripe_price_id: 'price_test',
  workos_user_id: 'user_test',
  status: 'active',
  start_date: new Date('2025-09-10T12:00:00.000Z'),
  billing_cycle_anchor: new Date('2025-09-10T12:00:00.000Z'),
  cancel_at: null,
  canceled_at: null,
  ended_at: null,
  trial_start: null,
  trial_end: null,
  created_at: new Date('2025-09-10T12:00:00.000Z'),
  updated_at: new Date('2025-09-10T12:00:00.000Z'),
  ...overrides,
});

const createMockSubscriptionStatus = (overrides = {}) => ({
  hasActiveSubscription: false,
  subscriptionId: null,
  status: null,
  currentPeriodStart: null,
  currentPeriodEnd: null,
  cancelAtPeriodEnd: false,
  plan: null,
  trialStart: null,
  trialEnd: null,
  ...overrides,
});

describe('Billing Service', () => {
  describe('calculateRemainingTrialEnd', () => {
    beforeEach(() => {
      // Mock the current time to ensure consistent test results
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2025-09-10T12:00:00.000Z'));
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should return full trial period for new tenant', () => {
      // Tenant created today
      const tenantCreatedAt = new Date('2025-09-10T12:00:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).not.toBeNull();
      if (result) {
        expect(result.getTime()).toBeGreaterThan(Date.now());

        // Calculate expected end the same way as the function
        const expectedTrialEnd = new Date(tenantCreatedAt);
        expectedTrialEnd.setDate(expectedTrialEnd.getDate() + 30);
        expectedTrialEnd.setHours(23, 59, 59, 999);
        expect(result.getTime()).toBe(expectedTrialEnd.getTime());
      }
    });

    it('should return remaining trial period for mid-trial tenant', () => {
      // Tenant created 15 days ago
      const tenantCreatedAt = new Date('2025-08-26T12:00:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).not.toBeNull();
      if (result) {
        expect(result.getTime()).toBeGreaterThan(Date.now());

        // Calculate expected end the same way as the function
        const expectedTrialEnd = new Date(tenantCreatedAt);
        expectedTrialEnd.setDate(expectedTrialEnd.getDate() + 30);
        expectedTrialEnd.setHours(23, 59, 59, 999);
        expect(result.getTime()).toBe(expectedTrialEnd.getTime());
      }
    });

    it('should return null for expired trial', () => {
      // Tenant created 31 days ago
      const tenantCreatedAt = new Date('2025-08-10T12:00:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).toBeNull();
    });

    it('should return remaining time for tenant with 1 day left', () => {
      // Tenant created 29 days ago
      const tenantCreatedAt = new Date('2025-08-12T12:00:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).not.toBeNull();
      if (result) {
        expect(result.getTime()).toBeGreaterThan(Date.now());

        // Calculate expected end the same way as the function
        const expectedTrialEnd = new Date(tenantCreatedAt);
        expectedTrialEnd.setDate(expectedTrialEnd.getDate() + 30);
        expectedTrialEnd.setHours(23, 59, 59, 999);
        expect(result.getTime()).toBe(expectedTrialEnd.getTime());
      }
    });

    it('should handle edge case of trial ending exactly now', () => {
      // Tenant created exactly 30 days ago
      const tenantCreatedAt = new Date('2025-08-11T12:00:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).toBeNull();
    });

    it('should round up to end of day for any remaining time', () => {
      // Tenant created 29.5 days ago (with time)
      const tenantCreatedAt = new Date('2025-08-11T23:30:00.000Z');
      const result = calculateRemainingTrialEnd(tenantCreatedAt);

      expect(result).not.toBeNull();
      if (result) {
        // Calculate expected end the same way as the function
        const expectedTrialEnd = new Date(tenantCreatedAt);
        expectedTrialEnd.setDate(expectedTrialEnd.getDate() + 30);
        expectedTrialEnd.setHours(23, 59, 59, 999);
        expect(result.getTime()).toBe(expectedTrialEnd.getTime());
      }
    });
  });

  describe('calculateTrialStatus', () => {
    const mockSubscriptions: SubscriptionRecord[] = [];

    beforeEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2025-09-10T12:00:00.000Z'));
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should calculate correct trial status for new tenant', () => {
      const trialStartedAt = new Date('2025-09-10T12:00:00.000Z');
      const result = calculateTrialStatus(trialStartedAt, mockSubscriptions);

      expect(result.isInTrial).toBe(true);
      expect(result.daysRemaining).toBe(30);
      expect(result.hasSubscription).toBe(false);
      expect(result.trialStartDate).toBe('2025-09-10T12:00:00.000Z');
      expect(result.trialEndDate).toBe('2025-10-10T12:00:00.000Z');
    });

    it('should calculate correct trial status for mid-trial tenant', () => {
      const trialStartedAt = new Date('2025-08-26T12:00:00.000Z');
      const result = calculateTrialStatus(trialStartedAt, mockSubscriptions);

      expect(result.isInTrial).toBe(true);
      expect(result.daysRemaining).toBe(15);
      expect(result.hasSubscription).toBe(false);
    });

    it('should calculate correct trial status for expired trial', () => {
      const trialStartedAt = new Date('2025-08-10T12:00:00.000Z');
      const result = calculateTrialStatus(trialStartedAt, mockSubscriptions);

      expect(result.isInTrial).toBe(false);
      expect(result.daysRemaining).toBe(0);
      expect(result.hasSubscription).toBe(false);
    });

    it('should detect when tenant has subscriptions', () => {
      const trialStartedAt = new Date('2025-09-10T12:00:00.000Z');
      const subscriptionsWithSub: SubscriptionRecord[] = [createMockSubscription()];

      const result = calculateTrialStatus(trialStartedAt, subscriptionsWithSub);

      expect(result.hasSubscription).toBe(true);
    });
  });

  describe('isBillingRequired', () => {
    it('should not require billing during trial period', () => {
      const trialStatus = {
        isInTrial: true,
        trialStartDate: '2025-09-10T12:00:00.000Z',
        trialEndDate: '2025-10-10T12:00:00.000Z',
        daysRemaining: 15,
        hasSubscription: false,
      };

      const subscriptionStatus = createMockSubscriptionStatus();

      const result = isBillingRequired(trialStatus, subscriptionStatus);
      expect(result).toBe(false);
    });

    it('should require billing after trial expires without subscription', () => {
      const trialStatus = {
        isInTrial: false,
        trialStartDate: '2025-08-10T12:00:00.000Z',
        trialEndDate: '2025-09-09T12:00:00.000Z',
        daysRemaining: 0,
        hasSubscription: false,
      };

      const subscriptionStatus = createMockSubscriptionStatus();

      const result = isBillingRequired(trialStatus, subscriptionStatus);
      expect(result).toBe(true);
    });

    it('should not require billing with active subscription', () => {
      const trialStatus = {
        isInTrial: false,
        trialStartDate: '2025-08-10T12:00:00.000Z',
        trialEndDate: '2025-09-09T12:00:00.000Z',
        daysRemaining: 0,
        hasSubscription: true,
      };

      const subscriptionStatus = createMockSubscriptionStatus({
        hasActiveSubscription: true,
        subscriptionId: 'sub_test',
        status: 'active',
        currentPeriodStart: '2025-09-10T12:00:00.000Z',
        currentPeriodEnd: '2025-10-10T12:00:00.000Z',
        plan: 'team',
      });

      const result = isBillingRequired(trialStatus, subscriptionStatus);
      expect(result).toBe(false);
    });
  });
});
