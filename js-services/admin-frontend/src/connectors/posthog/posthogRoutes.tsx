import { Route } from 'react-router-dom';
import { PostHogIntegrationPage } from './components/PostHogIntegrationPage';

export const POSTHOG_ROUTE_PATH = '/integrations/posthog';

export const posthogRoutes = [
  <Route
    key="posthog-integration"
    path={POSTHOG_ROUTE_PATH}
    element={<PostHogIntegrationPage />}
  />,
];
