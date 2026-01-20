import { Route } from 'react-router-dom';
import { AsanaIntegrationPage } from './components/AsanaIntegrationPage';

const asanaPath = '/integrations/asana';

const asanaRoutes = [
  <Route key="asana-integration" path={asanaPath} element={<AsanaIntegrationPage />} />,
];

export { asanaPath, asanaRoutes };
