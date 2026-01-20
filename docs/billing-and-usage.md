# Billing and Usage Tracking System

> **⚠️ This feature is OPTIONAL and disabled by default.**
>
> Grapevine works without any billing configuration. When billing is disabled, all tenants have unlimited usage. Only enable billing if you want to enforce usage limits or charge for subscriptions.
>
> See [Disabling Billing](#disabling-billing) for details on running without billing.

This document describes the integrated billing and usage tracking system for Grapevine, which manages subscription payments through Stripe and enforces usage limits based on subscription tiers.

## Disabling Billing

When billing is disabled (default), the system behaves as follows:

- **No usage limits**: All tenants can make unlimited requests
- **No billing UI**: Billing-related UI components are hidden
- **No Stripe integration**: No payment processing or subscription management
- **Simplified operations**: No need to manage subscriptions, trials, or usage tracking

To disable billing, simply don't set the `STRIPE_SECRET_KEY` environment variable. The `isBillingEnabled()` function will return `false`, and all billing-related functionality will be gracefully skipped.

## Setting Up Your Own Stripe Account

If you want to enable billing for your self-hosted Grapevine instance:

### 1. Create a Stripe Account

1. Sign up at [stripe.com](https://stripe.com)
2. Complete account verification

### 2. Create Products and Prices

In the Stripe Dashboard, create products for your subscription tiers:

1. Navigate to **Products** → **Add product**
2. Create products for each tier you want to offer (e.g., Team, Pro, Ultra)
3. For each product, create a recurring monthly price
4. Copy the Price IDs (they start with `price_`)

### 3. Configure Environment Variables

```bash
# Required for billing
STRIPE_SECRET_KEY=sk_live_...              # Your Stripe secret key
STRIPE_WEBHOOK_SECRET=whsec_...            # Webhook signing secret (see step 4)
FRONTEND_URL=https://your-domain.com       # For checkout redirect URLs

# Price IDs for each tier
STRIPE_PRICE_ID_TEAM_MONTHLY=price_...     # Team plan price ID
STRIPE_PRICE_ID_PRO_MONTHLY=price_...      # Pro plan price ID  
STRIPE_PRICE_ID_ULTRA_MONTHLY=price_...    # Ultra plan price ID
```

### 4. Set Up Webhooks

1. In Stripe Dashboard, go to **Developers** → **Webhooks**
2. Click **Add endpoint**
3. Enter your webhook URL: `https://your-domain.com/api/webhooks/billing/stripe`
4. Select events to listen for:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Copy the webhook signing secret and set it as `STRIPE_WEBHOOK_SECRET`

### 5. Configure Customer Portal

1. Go to **Settings** → **Billing** → **Customer portal**
2. Enable features you want customers to access:
   - Update payment method
   - View invoices
   - Cancel subscription

## ⚠️ Important: Redis Caching

**All billing and subscription data is cached in Redis.** Any manual changes to the database (tenant records, subscriptions, usage limits) require clearing the corresponding Redis cache keys to take effect immediately.

**The CLI commands handle this automatically** - they clear the relevant cache keys (`billing_limits:{tenant_id}`) after making changes.

If you make manual database changes outside the CLI, you must manually clear the cache:

```bash
# Clear billing limits cache for a tenant
redis-cli DEL billing_limits:abc123
```

## Runbooks

This section provides step-by-step procedures for common operational tasks.

### Extend a trial period

**Scenario**: A tenant's trial has expired or is about to expire, and you need to reset their trial period to give them additional time.

**Solution**: Use the `reset-trial` CLI command to reset the trial start date to the current time:

```bash
# Reset trial for a specific tenant
uv run python -m src.usage.cli reset-trial --tenant abc123
```

**What this does:**

1. **Updates trial_start_at**: Sets the `trial_start_at` field in the control database to the current timestamp, effectively giving a fresh 30-day trial period
2. **Clears billing cache**: Removes the Redis `billing_limits:{tenant_id}` cache key so that fresh billing limits are calculated on the next request
3. **Immediate effect**: The tenant will immediately have access to their full trial usage limits

**Prerequisites:**

- You need the tenant ID (16-character hexadecimal string)
- Access to the control database and Redis instance
- Environment variables configured (CONTROL_DATABASE_URL, Redis connection info)

**Verification:**
After running the command, you can verify the reset worked by:

1. Checking the tenant's billing status in the admin UI
2. Running a usage report for the tenant: `uv run python -m src.usage.cli report --tenant abc123`
3. The billing period should show the new trial start date

### Reset usage for a tenant

**Scenario**: A tenant has exhausted their monthly request limit and needs access restored before their next billing cycle.

**Solution**: Use the `reset-usage` command to reset their usage counter without affecting their trial/subscription timing:

```bash
# Reset usage for a specific tenant
uv run python -m src.usage.cli reset-usage --tenant abc123
```

**What this does:**

1. **Deletes usage records**: Removes all usage records from the tenant database
2. **Clears Redis cache**: Removes all Redis usage keys for the tenant (pattern: `usage:{tenant_id}:*`)
3. **Preserves billing**: Does NOT change their trial start date or subscription status
4. **Immediate effect**: The tenant will immediately have their usage reset to zero

**When to use this:**

- Tenant needs more requests mid-cycle due to unexpected usage
- You've negotiated additional usage as part of a deal
- Testing or troubleshooting scenarios
- Tenant is migrating from another system and initial usage spike is expected

**Prerequisites:**

- You need the tenant ID (16-character hexadecimal string)
- Access to the control database and Redis instance
- Environment variables configured (CONTROL_DATABASE_URL, Redis connection info)

**Verification:**
After running the command, you can verify the reset worked by:

1. Running a usage report: `uv run python -m src.usage.cli report --tenant abc123`
2. Checking that "Requests" shows 0 or very low numbers
3. Having the tenant test making a request through the system

**Note**: If the tenant is on a trial and you need to extend both their trial period AND reset usage, see the "Extend a trial period" section above.

### Check usage and trial status

**Solution**: Generate a detailed report for the specific tenant:

```bash
# Get detailed usage and billing information for a tenant
uv run python -m src.usage.cli report --tenant abc123

# Export as JSON
uv run python -m src.usage.cli report --tenant abc123 --format json --output report.json
```

This will show:

- Current usage metrics (requests used vs available)
- Billing limits and tier information
- Trial status and expiration dates
- Expired trial alerts (prominent red warnings)

### Generate a usage report for all tenants

**Solution**: Run the CLI without specifying a tenant:

```bash
# Generate report for all tenants
uv run python -m src.usage.cli report

# Export to JSON or CSV for analysis
uv run python -m src.usage.cli report --format json --output report.json
uv run python -m src.usage.cli report --format csv --output report.csv
```

The CLI queries usage data from the MCP `/v1/billing/usage` endpoint using JWT authentication.

### Configure custom request limits (Enterprise)

**Scenario**: A tenant has negotiated a custom contract with specific request limits outside of standard subscription tiers.

**How Enterprise Plans Work**: Enterprise plans are intentionally simple. The entire plan is controlled by a single field (`enterprise_plan_request_limit`) in the tenant's record. When this field is set, it takes precedence over all other billing settings (Stripe subscriptions, trial limits, etc.). Setting a plan is just a matter of setting this value for the tenant and clearing the Redis cache. Clearing a plan is equally simple: set the value to NULL and clear the cache.

**Solution**: Use the `set-enterprise-plan` CLI command to configure custom limits:

```bash
# Set enterprise plan with 50,000 monthly requests
uv run python -m src.usage.cli set-enterprise-plan abc123 50000
```

**What this does:**

1. **Sets custom limit**: Updates the `enterprise_plan_request_limit` field in the control database with the specified monthly request limit
2. **Takes precedence**: Enterprise plans override any existing Stripe subscriptions or trial limits
3. **Clears billing cache**: Removes the Redis `billing_limits:{tenant_id}` cache key so new limits take effect immediately

**Prerequisites:**

- You need the tenant ID (16-character hexadecimal string)
- Negotiated request limit
- Access to the control database and Redis instance
- Environment variables configured (CONTROL_DATABASE_URL, Redis connection info)

**Verification:**
After running the command, you can verify the enterprise plan is active:

```bash
# Check enterprise plan status
uv run python -m src.usage.cli show-enterprise-plan abc123
```

This will display a formatted table showing:

- Tenant ID
- Enterprise Plan status and request limit
- Creation and update timestamps

**Removing an enterprise plan:**
If a tenant downgrades from enterprise to standard billing:

```bash
# Remove enterprise plan (reverts to standard billing)
uv run python -m src.usage.cli remove-enterprise-plan abc123
```

### Create discount codes

**Scenario**: You want to offer a discount on subscriptions.

**Solution**: Create a coupon code in the Stripe Dashboard:

1. **Navigate to Stripe Dashboard** → **Products** → **Coupons**

2. **Create a new coupon:**
   - Click "Create coupon" button
   - Choose discount type:
     - **Percentage discount**: e.g., 20% off
     - **Fixed amount discount**: e.g., $50 off
   - Set duration:
     - **Once**: Applies to first invoice only
     - **Forever**: Applies to all invoices
     - **Repeating**: Applies for a specific number of months
   - Enter a coupon code (e.g., `WELCOME20`, `EARLYBIRD50`)
   - Optionally set redemption limits and expiration dates

3. **Share the coupon code** with users

4. **Users apply the coupon:**
   - During checkout: Enter the code in the promotional code field
   - In billing settings: Apply the code to an existing subscription

**What this does:**

- Creates a reusable discount code in Stripe
- Allows users to self-serve discounts through the UI
- Automatically applies the discount to invoices based on the duration settings
- Tracks coupon usage and redemptions in Stripe Dashboard

## Data Model

### Control Database

The **control database** stores cross-tenant billing and subscription data:

- **`tenants` table**: Tenant records with billing configuration

  - `enterprise_plan_request_limit`: Custom monthly request limit for enterprise (overrides all other limits)
  - `trial_start_at`: Trial period start timestamp
  - `created_at`: Tenant creation timestamp (used for trial calculations)

- **`subscriptions` table**: Stripe subscription records
  - `stripe_subscription_id`: Stripe subscription reference
  - `stripe_customer_id`: Stripe customer reference
  - `status`: Subscription status (active, canceled, past_due, etc.)
  - `billing_cycle_anchor`: Stripe billing period start (used for usage period calculations)
  - `plan_id`: Subscription tier (team, pro, ultra)

### Tenant Databases

Each tenant has their own database with a **`usage_records` table** for tracking consumption:

- `tenant_id`: Tenant identifier
- `metric_type`: Type of usage (requests, input_tokens, output_tokens, embedding_tokens)
- `metric_value`: Usage count
- `billing_period_start`: Start of the billing period (from subscription or trial)
- `timestamp`: When the usage was recorded

### Caching Layer

**Redis** provides high-performance caching with the following keys:

- `billing_limits:{tenant_id}`: Cached billing tier, limits, and subscription status
- `usage:{tenant_id}:{metric_type}:{billing_period_start_date}`: Real-time usage counters
  - Automatically expires after 3 months
  - Atomic INCR operations for thread-safe updates
  - Falls back to database when Redis unavailable

## Architecture

### Overview

The system provides:

- **Subscription Management**: Create and manage subscriptions via Stripe Checkout
- **Usage Tracking**: Monitor API calls, tokens, and other metrics across tenants
- **Usage Enforcement**: Real-time limits based on subscription tiers
- **Trial Period Support**: 30-day grace period with automatic carryover to subscriptions
- **Multi-tenant Support**: Per-organization billing tied to tenant lifecycle

### Core Components

#### Billing System (`js-services/admin-backend/`)

**Billing Service** (`src/services/billing-service.ts`)

- Trial logic calculation using tenant creation timestamps
- Active subscription resolution and status formatting
- Multi-tier product configuration (Team, Pro, Ultra)
- Dynamic product availability based on environment variables

**Billing API** (`src/controllers/billing.ts`)

- Stripe Checkout session creation with trial carryover
- Subscription management (cancel/reactivate)
- Billing status endpoint with trial and usage information

**Webhook Handler** (`src/controllers/webhooks.ts`)

- Stripe event processing for subscription lifecycle
- Automatic cache invalidation for billing limits

#### Usage Tracking System (`src/utils/usage_tracker.py`)

**Redis-First Architecture**

- Primary storage in Redis with billing period keys
- Database fallback for durability and maintenance windows
- Atomic INCR operations for thread-safe usage recording
- Automatic key expiration (3 months) for cleanup

**Usage Metrics**

- Requests: API calls to `ask_agent` tools
- Input/Output Tokens: LLM usage tracking
- Embedding Tokens: Document ingestion processing

### Data Flow

#### Billing Period Logic

The system uses **billing periods** rather than calendar months:

- **For Subscriptions**: Usage resets based on `billing_cycle_anchor` from Stripe
- **For Trials**: Usage resets based on `trial_start_at` date
- **Key Structure**: `usage:{tenant_id}:{metric_type}:{billing_period_start_date}`

#### Usage Enforcement

1. **Pre-request Check**: Verify current usage against subscription limits
2. **Real-time Recording**: Atomic Redis operations for immediate tracking
3. **Fallback Behavior**: Database queries when Redis unavailable
4. **Fail-open Design**: Allow requests when both systems down

#### Trial Carryover

When users subscribe during trial, remaining trial days automatically apply to Stripe subscription:

- No immediate billing until original trial expires
- Maximum user benefit with end-of-day rounding

## Key File Locations

### Backend (Python)

- `src/utils/billing_limits.py` - Billing limits tracking (billing tier, metric limits)
- `src/utils/usage_tracker.py` - Core usage tracking service
- `src/mcp/tools/ask_agent.py` - Request-level usage integration
- `src/steward/models.py` - Tenant billing mode management
- `migrations/control/` - Control database schema
- `migrations/tenant/` - Per-tenant usage tracking schema

### Admin Backend (TypeScript)

- `js-services/admin-backend/src/services/billing-service.ts` - Billing logic
- `js-services/admin-backend/src/controllers/billing.ts` - API endpoints
- `js-services/admin-backend/src/controllers/webhooks.ts` - Stripe webhooks
- `js-services/admin-backend/src/dal/subscriptions.ts` - Database operations

### Frontend (React)

- `js-services/admin-frontend/src/components/BillingPage.tsx` - UI
- `js-services/admin-frontend/src/hooks/useBillingStatus.ts` - API integration

## Configuration

### Environment Variables

**Required for Billing:**

- `STRIPE_SECRET_KEY` - Stripe API access
- `STRIPE_WEBHOOK_SECRET` - Webhook signature verification
- `FRONTEND_URL` - Checkout redirect URLs

**Product Configuration:**

- `STRIPE_PRICE_ID_TEAM_MONTHLY` - Team plan price ID
- `STRIPE_PRICE_ID_PRO_MONTHLY` - Pro plan price ID
- `STRIPE_PRICE_ID_ULTRA_MONTHLY` - Ultra plan price ID

**Usage Tracking:**

- `REDIS_PRIMARY_ENDPOINT` - Redis connection for usage cache
- `CONTROL_DATABASE_URL` - Cross-tenant operations
- Individual tenant database connections

### Feature Flags

**`ENABLE_BILLING_USAGE_UI`** (boolean, default: `false`)

Controls whether the usage section is visible in the billing UI.

- **When enabled (`true`)**: Usage section displayed in billing page
- **When disabled (`false`)**: Usage section hidden from billing page

Note: Billing limits are automatically enabled when billing is configured (`STRIPE_SECRET_KEY` is set). When billing is disabled, all tenants get unlimited usage.

## Development Workflow

### Webhook Testing

```bash
# Forward webhooks locally
stripe listen --forward-to localhost:5173/api/webhooks/billing/stripe

# Test events
stripe trigger customer.subscription.created
```

Copy and paste the stripe webhook secret, and run:

```bash
STRIPE_WEBHOOK_SECRET=wh_sec... mise dev
```

## Trade-offs and Design Decisions

### Storage Architecture: Redis + Database

**Benefits:**

- ✅ High-performance usage tracking with atomic operations
- ✅ Automatic fallback during maintenance windows
- ✅ Real-time usage enforcement for subscription limits

**Trade-offs:**

- ❌ More complex failure handling vs database-only approach
- ✅ Mitigated by fail-open design and auto-recovery

### Billing Period vs Calendar Month

**Decision**: Use subscription `billing_cycle_anchor` for usage periods

**Benefits:**

- ✅ Usage limits align with actual billing cycles
- ✅ Fair usage calculation for mid-month subscriptions
- ✅ Consistent with Stripe billing model

**Trade-offs:**

- ❌ More complex period calculation vs calendar months
- ❌ Requires Stripe metadata for period determination

### Control DB vs Tenant DB for Usage

**Current Design**: Usage records in individual tenant databases

**Benefits:**

- ✅ Natural tenant isolation and data sovereignty
- ✅ Scales horizontally with tenant growth
- ✅ Aligns with existing multi-tenant architecture

**Trade-offs:**

- ❌ Cross-tenant analytics require aggregation
- ❌ More complex than single database approach

## Monitoring and Troubleshooting

### Key Metrics

**System Health:**

- Redis availability and cache hit rates
- Database fallback frequency
- Usage recording error rates

**Business Metrics:**

- Usage vs subscription limits by tenant
- Trial conversion rates
- Payment success/failure rates

### Common Issues

**Webhook Failures:**

- Verify `STRIPE_WEBHOOK_SECRET` matches your Stripe Dashboard
- Check endpoint URL and raw body parsing

## Future Improvements

**Remaining:**

- Billing UI to show available requests / total requests
- Usage-based billing (UBB) beyond fixed tier limits
- Advanced usage analytics and reporting features
