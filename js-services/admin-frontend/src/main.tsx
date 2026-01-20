import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { App } from './App';
import { initializeAnalytics, newrelic } from '@corporate-context/frontend-common';
import type { FeatureFlag } from './hooks/useFeatureFlag';

// Initialize monitoring services before rendering the app
newrelic.initialize();
initializeAnalytics();

// Add __grapevineDev__ global for feature flag management
declare global {
  interface Window {
    __grapevineDev__: {
      enableFlag: (flag: FeatureFlag) => void;
      disableFlag: (flag: FeatureFlag) => void;
    };
  }
}

window.__grapevineDev__ = {
  enableFlag: (flag: FeatureFlag) => {
    localStorage.setItem(flag, 'true');
    console.log(`Feature flag "${flag}" enabled. Refresh the page to see changes.`);
  },
  disableFlag: (flag: FeatureFlag) => {
    localStorage.removeItem(flag);
    console.log(`Feature flag "${flag}" disabled. Refresh the page to see changes.`);
  },
};

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
