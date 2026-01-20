import { Route } from 'react-router-dom';
import { ZendeskIntegrationPage } from './components/ZendeskIntegrationPage/ZendeskIntegrationPage';

const zendeskPath = '/integrations/zendesk';

const zendeskRoutes = [
  <Route key="zendesk-integration" path={zendeskPath} element={<ZendeskIntegrationPage />} />,
];

export { zendeskRoutes, zendeskPath };
