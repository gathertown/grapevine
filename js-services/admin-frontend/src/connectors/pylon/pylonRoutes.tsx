import { Route } from 'react-router-dom';
import { PylonIntegrationPage } from './components/PylonIntegrationPage';

const pylonPath = '/integrations/pylon';

const pylonRoutes = [
  <Route key="pylon-integration" path={pylonPath} element={<PylonIntegrationPage />} />,
];

export { pylonPath, pylonRoutes };
