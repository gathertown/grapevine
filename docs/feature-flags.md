# Feature Flags

A lightweight feature flag system for the admin frontend to gate features during development.

## Goals

- Work on features in isolation without shipping incomplete functionality to customers
- Manually enable/disable features via console commands for testing in production/staging

## Non-Goals (for now)

- Percentage rollouts or user cohorts
- Third-party integrations

## Design Philosophy

This is the simplest possible implementation that can be easily replaced later without breaking changes.

# Usage

## Turning on / off a feature flag

### Manual localStorage (not recommended)

- `window.localStorage.setItem("billing-ui", "true")`
- `window.localStorage.removeItem("billing-ui")`

### Using dev console (recommended)

- `window.__grapevineDev__.enableFlag("billing-ui")`
- `window.__grapevineDev__.disableFlag("billing-ui")`

## Consuming a flag

```tsx
import { useFeatureFlag } from './hooks/useFeatureFlag';

const isBillingEnabled = useFeatureFlag('billing-ui');
```

## Implementation Notes

- Feature flags are strongly typed via the `FeatureFlag` union type in `src/hooks/useFeatureFlag.ts`
- Page refresh is required after enabling/disabling flags
