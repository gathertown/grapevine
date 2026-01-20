import { Route } from 'react-router-dom';
import { ClickupIntegrationPage } from './components/ClickupIntegrationPage';

const clickupPath = '/integrations/clickup';

const clickupRoutes = [
  <Route key="clickup-integration" path={clickupPath} element={<ClickupIntegrationPage />} />,
];

export { clickupPath, clickupRoutes };
