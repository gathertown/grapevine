import { Route } from 'react-router-dom';
import { CanvaIntegrationPage } from './components/CanvaIntegrationPage';

const canvaPath = '/integrations/canva';

const canvaRoutes = [
  <Route key="canva-integration" path={canvaPath} element={<CanvaIntegrationPage />} />,
];

export { canvaPath, canvaRoutes };
