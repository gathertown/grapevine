# Amplitude Integration in Admin Frontend

This document describes the Amplitude Browser SDK integration with session replay capabilities.

## Configuration

The integration is configured to:

- Only run in staging and production environments (disabled in local/development)
- Collect user identification from WorkOS authentication
- Enable session replay with privacy controls
- Provide a React hook for custom event tracking

## Environment Variables

Add the following environment variable:

- `VITE_AMPLITUDE_API_KEY`: Your Amplitude project API key

## Usage

### Tracking Custom Events

```typescript
import { useAmplitude, AmplitudeEvents } from '../hooks/useAmplitude';

const MyComponent = () => {
  const { track, trackClick, trackPageView, isEnabled } = useAmplitude();

  const handleButtonClick = () => {
    trackClick('save-button', {
      page: 'onboarding',
      step: 'configuration'
    });

    // Or use predefined events
    track(AmplitudeEvents.DATA_SOURCE_CONFIGURED, {
      source: 'github',
      success: true
    });
  };

  return (
    <button onClick={handleButtonClick}>Save</button>
  );
};
```

### Privacy Controls

Use these CSS classes to control what data is recorded in session replays:

```tsx
// Block entire element from recording
<div className="amp-block sensitive-data">
  This content will not appear in session replays
</div>

// Mask text content (element structure is recorded but text is hidden)
<div className="amp-mask user-info">
  This text will be masked: user@email.com
</div>
```

### Automatic Tracking

The following is tracked automatically:

- Page views (when enabled)
- User identification on login/logout
- Session data
- File downloads

### Pre-defined Events

Common events are defined in `AmplitudeEvents`:

- `ONBOARDING_STARTED`
- `DATA_SOURCE_CONFIGURED`
- `USER_SIGNED_IN`
- `ERROR_OCCURRED`
- And more...

## Session Replay Privacy

Session replay is configured with:

- 100% sample rate to capture all sessions
- Automatic blocking of password inputs
- Masking of sensitive form fields
- Respect for `.amp-block` and `.amp-mask` CSS classes

## Implementation Details

- **Service**: `src/services/amplitude.ts` - Core Amplitude initialization
- **Hook**: `src/hooks/useAmplitude.ts` - React hook for event tracking
- **Integration**: `src/contexts/AuthContext.tsx` - User identification
- **Initialization**: `src/main.tsx` - App-level initialization
