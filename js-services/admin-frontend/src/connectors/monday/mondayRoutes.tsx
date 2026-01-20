import { Route } from 'react-router-dom';
import { MondayIntegrationPage } from './components/MondayIntegrationPage';

const mondayPath = '/integrations/monday';

const mondayRoutes = [
  <Route key="monday-integration" path={mondayPath} element={<MondayIntegrationPage />} />,
];

export { mondayPath, mondayRoutes };
