# Feature Configuration Guide

This guide describes how to configure Grapevine's features for self-hosted deployments. The system is designed with sensible defaults—most optional features are disabled by default, allowing you to start with minimal configuration and enable additional capabilities as needed.

## Minimal Configuration (Getting Started)

To run Grapevine with the bare minimum configuration, you only need these core services:

| System          | Required Env Vars                       | Purpose                                     |
| --------------- | --------------------------------------- | ------------------------------------------- |
| **PostgreSQL**  | `CONTROL_DATABASE_URL`                  | Control database for tenants, configuration |
| **OpenSearch**  | `OPENSEARCH_DOMAIN_HOST`, credentials   | Full-text keyword search                    |
| **Turbopuffer** | `TURBOPUFFER_API_KEY`, `TURBOPUFFER_REGION` | Vector database for semantic search     |
| **Redis**       | `REDIS_PRIMARY_ENDPOINT`                | Session cache, rate limiting, job state     |
| **OpenAI**      | `OPENAI_API_KEY`                        | Embeddings and AI                           |
| **AWS SQS**     | `*_JOBS_QUEUE_ARN`                      | Async job processing                        |
| **AWS SSM**     | `KMS_KEY_ID`                            | Secure credential storage                   |
| **WorkOS**      | `WORKOS_API_KEY`, `WORKOS_CLIENT_ID`    | Authentication & SSO                        |

> **Note**: For local development, you can use LocalStack to emulate AWS services (SQS, SSM, KMS) without an AWS account.

## Optional Features Overview

All features below are **disabled by default** and can be enabled by setting the appropriate environment variables. None of these are required for Grapevine to function.

| Feature                   | Required Env Vars                            | Default  | Purpose                        |
| ------------------------- | -------------------------------------------- | -------- | ------------------------------ |
| **Billing/Stripe**        | `STRIPE_SECRET_KEY`                          | Disabled | Subscription management        |
| **Analytics (Amplitude)** | `VITE_AMPLITUDE_API_KEY`                     | Disabled | User analytics                 |
| **Analytics (PostHog)**   | `VITE_POSTHOG_API_KEY`, `VITE_POSTHOG_HOST`  | Disabled | Product analytics              |
| **Email (Mailgun)**       | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`          | Disabled | Invitation emails              |
| **Langfuse Tracing**      | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Disabled | LLM observability              |
| **New Relic (Backend)**   | `NEW_RELIC_LICENSE_KEY`                      | Disabled | Application monitoring         |
| **New Relic (Frontend)**  | `VITE_NEW_RELIC_*` (all 5 required)          | Disabled | Browser performance monitoring |

## Billing (Stripe) — Optional

Enables subscription management, payment processing, and usage limits. **When disabled, all tenants have unlimited usage.**

See [Billing and Usage](./billing-and-usage.md) for detailed setup instructions.

**Environment Variables:**

- `STRIPE_SECRET_KEY` - Stripe API secret key (presence enables billing)
- `STRIPE_PRICE_ID_*_MONTHLY` - Price IDs for different tiers

**Behavior when disabled (default):**

- `isBillingEnabled()` returns `false`
- Billing UI components are not rendered
- All tenants have unlimited usage (no limits enforced)
- Stripe client returns `null` from `getOrInitializeStripe()`

**Behavior when enabled:**

- Enforces per-tier limits: trial (300), basic (200), team (500), pro (4,000), ultra (15,000)
- Subscription management UI is available
- Usage tracking is enforced

## Analytics — Optional

All analytics integrations are optional and disabled by default. Grapevine operates fully without any analytics configured.

### Amplitude

Provides user analytics and session replay.

**Environment Variables:**

- `VITE_AMPLITUDE_API_KEY` - API key for Amplitude

**Behavior when disabled (default):**

- Analytics calls are no-ops
- No error messages in console (just a warning on init)
- All tracking functions safely return without action

### PostHog

Provides product analytics and feature flags.

**Environment Variables:**

- `VITE_POSTHOG_API_KEY` - API key for PostHog
- `VITE_POSTHOG_HOST` - PostHog host URL (default: `https://us.i.posthog.com`)
- `VITE_POSTHOG_UI_HOST` - PostHog UI host URL

**Behavior when disabled (default):**

- Analytics calls are no-ops
- Python `PostHogService.is_initialized` returns `False`
- All tracking methods log warnings and return without action

## Email Delivery (Mailgun) — Optional

Invitation emails can be sent via WorkOS and/or Mailgun.

**How it works:**

- WorkOS always creates the invitation record
- WorkOS may send emails based on its platform configuration (configured in WorkOS dashboard, not in code)
- If Mailgun is configured, emails are also sent via Mailgun

**Environment Variables:**

- `MAILGUN_API_KEY` - Mailgun API key
- `MAILGUN_DOMAIN` - Mailgun domain
- `MAILGUN_FROM_EMAIL` - From email address (defaults to `noreply@{MAILGUN_DOMAIN}`)

**Behavior when disabled (default):**

- Invitations still work (WorkOS creates the invitation record regardless of email config)
- The `/api/invitations/status` endpoint reports Mailgun is not configured
- WorkOS may still send invitation emails via its own platform configuration

**Example Configuration:**

```bash
# Enable Mailgun email delivery
MAILGUN_API_KEY=your-mailgun-api-key
MAILGUN_DOMAIN=mail.yourdomain.com
```

## Langfuse Tracing — Optional

Provides LLM observability and tracing for debugging AI interactions.

**Environment Variables:**

- `TRACING_ENABLED=true` - Enable tracing (default: `true`)
- `LANGFUSE_PUBLIC_KEY` - Langfuse public key
- `LANGFUSE_SECRET_KEY` - Langfuse secret key
- `LANGFUSE_HOST` - Langfuse host URL (default: `https://us.cloud.langfuse.com`)

**Behavior when disabled (default):**

- `trace_span()` context manager yields a `NoOpSpan`
- No tracing data is sent
- Performance impact is minimal

## New Relic — Optional

Provides application performance monitoring. Completely optional for self-hosted deployments.

### Backend (Python)

**Environment Variables:**

- `NEW_RELIC_LICENSE_KEY` - New Relic license key

**Configuration:**

- Configured via `newrelic.toml` files per service
- `monitor_mode = false` for local/dev/test environments
- Automatically disabled when license key is missing

**Behavior when disabled (default):**

- New Relic agent runs in stub mode
- No data is sent to New Relic
- `newrelic.agent.record_exception()` calls are safe no-ops

### Frontend (Browser)

New Relic is automatically enabled when all required configuration is present.

**Environment Variables:**

- `VITE_NEW_RELIC_LICENSE_KEY` - License key
- `VITE_NEW_RELIC_APPLICATION_ID` - Application ID
- `VITE_NEW_RELIC_ACCOUNT_ID` - Account ID
- `VITE_NEW_RELIC_TRUST_KEY` - Trust key
- `VITE_NEW_RELIC_AGENT_ID` - Agent ID

**Behavior when not configured (default):**

- Browser agent is not initialized
- All monitoring functions are safe no-ops

### Backend (Node.js)

**Environment Variables:**

- `NEW_RELIC_LICENSE_KEY` - License key

**Behavior when disabled (default):**

- `isNewRelicEnabled` returns `false`
- `initializeNewRelicIfEnabled()` returns `undefined`
- New Relic module is not imported

## Checking Feature Status

### JavaScript/TypeScript

```typescript
import { isBillingEnabled } from './utils/config';
import { isNewRelicEnabled } from '@corporate-context/backend-common';

if (isBillingEnabled()) {
  // Billing-specific logic
}

if (isNewRelicEnabled) {
  // New Relic-specific logic
}
```

### Python

```python
from src.utils.config import get_billing_enabled, get_amplitude_enabled

if get_billing_enabled():
    # Billing-specific logic
    pass
```

## Feature Flag Development

For feature flags during development, see [Feature Flags](./feature-flags.md).
