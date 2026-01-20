# New Relic Browser Monitoring Integration

This document explains the New Relic Browser monitoring integration for the Grapevine admin frontend.

## Overview

New Relic Browser monitoring provides real-user monitoring (RUM) for the admin frontend, tracking:

- Page load times and Core Web Vitals
- JavaScript errors and stack traces
- AJAX requests and API performance
- User interactions and custom events
- SPA route changes and navigation
- User sessions and behavior flows

## Setup

New Relic is automatically enabled when all required configuration is present. Configure with the following env vars:

```env
VITE_NEW_RELIC_LICENSE_KEY
VITE_NEW_RELIC_APPLICATION_ID
VITE_NEW_RELIC_ACCOUNT_ID
VITE_NEW_RELIC_TRUST_KEY
VITE_NEW_RELIC_AGENT_ID
```

When all these variables are set, New Relic monitoring is automatically enabled. If any are missing, monitoring is disabled.

## Features

### Automatic Tracking

The integration automatically tracks:

- **Page views**: All route changes in the SPA
- **JavaScript errors**: Unhandled exceptions and promise rejections
- **AJAX requests**: API calls to the backend
- **User sessions**: Session duration and behavior
- **Performance metrics**: Page load times, resource loading

### Custom Event Tracking

Use the `newrelic` object directly for tracking custom events:

```typescript
import { newrelic } from '@corporate-context/frontend-common';

// Track integration setup
newrelic.addPageAction('integrationSetup', {
  integrationType: 'github',
  status: 'completed',
});

// Track file uploads
newrelic.addPageAction('fileUpload', {
  fileType: 'csv',
  fileSize: 1024000,
  status: 'completed',
});

// Track any custom action
newrelic.addPageAction('button-click', {
  buttonName: 'save-settings',
  section: 'integrations',
});
```

### Error Handling

You can manually record errors to New Relic:

```typescript
import { newrelic } from '@corporate-context/frontend-common';

try {
  // Some operation that might fail
} catch (error) {
  newrelic.recordError(error as Error, {
    context: 'integration-setup',
    integrationType: 'github',
  });
}
```

### User Context

User information is automatically attached to all events when users authenticate:

- User ID
- Organization ID
- Organization Name
- Tenant ID
- Has Organization status

## Privacy and Security
