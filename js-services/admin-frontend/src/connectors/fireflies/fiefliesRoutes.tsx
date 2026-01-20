import { Route } from 'react-router-dom';
import { FirefliesIntegrationPage } from './components/FirefliesIntegrationPage';

const firefliesPath = '/integrations/fireflies';

const firefliesRoutes = [
  <Route key="fireflies-integration" path={firefliesPath} element={<FirefliesIntegrationPage />} />,
];

export { firefliesPath, firefliesRoutes };
